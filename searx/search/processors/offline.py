# SPDX-License-Identifier: AGPL-3.0-or-later
"""Processors for engine-type: ``offline``

"""

from searx.enginelib.engine import EngineModule
from .abstract import EngineProcessor


class OfflineProcessor(EngineProcessor):
    """Processor class used by ``offline`` engines"""

    engine_type = 'offline'

    def _search_basic(self, query, params):
        if isinstance(self.engine, EngineModule):
            return self.engine.search(query, params)
        raise NotImplementedError(f"search is not implemented for engine of type: {self.engine.__class__.__name__}")

    def search(self, query, params, result_container, start_time, timeout_limit):
        try:
            search_results = self._search_basic(query, params)
            self.extend_container(result_container, start_time, search_results)
        except ValueError as e:
            # do not record the error
            self.logger.exception('engine {0} : invalid input : {1}'.format(self.engine_name, e))
        except Exception as e:  # pylint: disable=broad-except
            self.handle_exception(result_container, e)
            self.logger.exception('engine {0} : exception : {1}'.format(self.engine_name, e))
