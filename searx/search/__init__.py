# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, too-few-public-methods

# the public namespace has not yet been finally defined ..
# __all__ = ["SearchQuery"]

import threading
from timeit import default_timer
from uuid import uuid4

from flask import copy_current_request_context

from searx import logger
from searx import get_setting
import searx.answerers
import searx.plugins
import searx.metrics

from searx.engines import load_engines
from searx.extended_types import SXNG_Request
from searx.external_bang import get_bang_url
from searx.results import ResultContainer
from searx.search.models import SearchQuery
from searx.search.processors import PROCESSORS


from .models import SearchQuery

logger = logger.getChild('search')


def initialize(settings_engines=None, enable_checker=False, check_network=False, enable_metrics=True):

    import searx.network
    import searx.search.checker
    import searx.metrics
    import searx.search.processors

    settings_engines = settings_engines or get_setting("engines")
    load_engines(settings_engines)
    searx.network.initialize(settings_engines, get_setting("outgoing"))
    searx.metrics.initialize([engine['name'] for engine in settings_engines], enable_metrics)
    searx.search.processors.initialize(settings_engines)

    if check_network:
        searx.network.check_network_configuration()
    if enable_checker:
        searx.search.checker.initialize()


class Search:
    """Search information container"""

    __slots__ = "search_query", "result_container", "start_time", "actual_timeout"

    def __init__(self, search_query: SearchQuery):
        """Initialize the Search"""
        # init vars
        super().__init__()
        self.search_query = search_query
        self.result_container = ResultContainer()
        self.start_time: float = None  # type: ignore
        self.actual_timeout: float = None  # type: ignore

    def search_external_bang(self):
        """
        Check if there is a external bang.
        If yes, update self.result_container and return True
        """
        if self.search_query.external_bang:
            self.result_container.redirect_url = get_bang_url(self.search_query)

            # This means there was a valid bang and the
            # rest of the search does not need to be continued
            if isinstance(self.result_container.redirect_url, str):
                return True
        return False

    def search_answerers(self):

        results = searx.answerers.STORAGE.ask(self.search_query.query)
        self.result_container.extend_results("answerers", results)
        return bool(results)

    # do search-request
    def _get_requests(self):
        # init vars
        requests = []

        # max of all selected engine timeout
        default_timeout = 0

        # start search-request for all selected engines
        for eng_name in self.search_query.engine_names:  # FIXME
            processor = PROCESSORS[eng_name]

            # stop the request now if the engine is suspend
            if processor.extend_container_if_suspended(self.result_container):
                continue

            # set default request parameters
            request_params = processor.get_params(self.search_query)
            if request_params is None:
                continue

            searx.metrics.counter_inc('engine', eng_name, 'search', 'count', 'sent')

            # append request to list
            requests.append((eng_name, self.search_query.query, request_params))

            # update default_timeout
            default_timeout = max(default_timeout, processor.engine.timeout)

        # adjust timeout
        max_request_timeout = get_setting("outgoing.max_request_timeout")
        actual_timeout = default_timeout
        query_timeout = self.search_query.timeout_limit

        if max_request_timeout is None and query_timeout is None:
            # No max, no user query: default_timeout
            pass
        elif max_request_timeout is None and query_timeout is not None:
            # No max, but user query: From user query except if above default
            actual_timeout = min(default_timeout, query_timeout)
        elif max_request_timeout is not None and query_timeout is None:
            # Max, no user query: Default except if above max
            actual_timeout = min(default_timeout, max_request_timeout)
        elif max_request_timeout is not None and query_timeout is not None:
            # Max & user query: From user query except if above max
            actual_timeout = min(query_timeout, max_request_timeout)

        logger.debug(
            "actual_timeout={0} (default_timeout={1}, ?timeout_limit={2}, max_request_timeout={3})".format(
                actual_timeout, default_timeout, query_timeout, max_request_timeout
            )
        )

        return requests, actual_timeout

    def search_multiple_requests(self, requests):
        # pylint: disable=protected-access
        search_id = str(uuid4())

        for engine_name, query, request_params in requests:
            _search = copy_current_request_context(PROCESSORS[engine_name].search)
            th = threading.Thread(  # pylint: disable=invalid-name
                target=_search,
                args=(query, request_params, self.result_container, self.start_time, self.actual_timeout),
                name=search_id,
            )
            th._timeout = False  # type: ignore
            th._engine_name = engine_name  # type: ignore
            th.start()

        for th in threading.enumerate():  # pylint: disable=invalid-name
            if th.name == search_id:
                remaining_time = max(0.0, self.actual_timeout - (default_timer() - self.start_time))
                th.join(remaining_time)
                if th.is_alive():
                    th._timeout = True  # type: ignore
                    _eng_name = th._engine_name  # type: ignore
                    self.result_container.add_unresponsive_engine(_eng_name, 'timeout')
                    PROCESSORS[_eng_name].logger.error('engine timeout')

    def search_standard(self):
        """
        Update self.result_container, self.actual_timeout
        """
        requests, self.actual_timeout = self._get_requests()

        # send all search-request
        if requests:
            self.search_multiple_requests(requests)

        # return results, suggestions, answers and infoboxes
        return True

    # do search-request
    def search(self) -> ResultContainer:
        self.start_time = default_timer()
        if not self.search_external_bang():
            if not self.search_answerers():
                self.search_standard()
        return self.result_container


class SearchWithPlugins(Search):
    """Inherit from the Search class, add calls to the plugins."""

    def __init__(self, search_query: SearchQuery, sxng_request: SXNG_Request):
        super().__init__(search_query)
        self.result_container.on_result = self._on_result
        self.request = sxng_request

    def _on_result(self, result):
        return searx.plugins.STORAGE.on_result(self.request, self, result)

    def search(self) -> ResultContainer:

        if searx.plugins.STORAGE.pre_search(self.request, self):
            super().search()

        searx.plugins.STORAGE.post_search(self.request, self)
        self.result_container.close()

        return self.result_container
