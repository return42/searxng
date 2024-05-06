
class SQLiteTable:

    def struct2rows(self, data):
        p_idx = 0
        row_list = []

        def _dict2row(self, d):
            p_idx = p_idx +1

            for k, v in d.items():
                row = {}
                row[self.pkeys[p_idx]] = k
                p_idx += 1
                if not isinstance(v, dict):
                    row[self.pkeys[p_idx]] = v
                else:
                    row.update(self._dict2row(v))
            return row
        FIXME  / TODO

    def __init__(self, table_name, col_def_list):

        # https://www.sqlite.org/datatype3.html
        # col_def_list = [
        #     # (col_name, is_pkey, col_type, default)
        #     ('id', True , 'INTEGER', None),
        #     ('name', False , 'TEXT', None),
        # ]

        self.table_name = table_name
        self.col_def_list = col_def_list

        self.pkeys = []
        self.col_names = []
        self.sql_create = None
        self.sql_create_idx = None

        self.init_ddl()

    def sql_select_row(self, **kwargs):

        where_cols = []
        where_values = []

        for _key in self.pkeys:
            if _key not in kwargs:
                raise ValueError('missing primary key: %s' % _key)
            where_cols.append(_key)
            where_values.append(kwargs[_key])

        sql = (
            "SELECT %s" % (', '.join(self.col_names))
            + " FROM %s" % (self.table_name)
            + " WHERE " + " AND ".join(["%s=?" % c for c in where_cols])
        )
        return sql, where_values

    def sql_update_row(self, **kwargs):

        where_cols = []
        where_values = []
        upd_cols = []
        upd_values = []
        _keys = self.pkeys[:]

        for col_name, col_value in kwargs.items():
            if col_name in _keys:
                _keys.remove(col_name)
                where_cols.append(col_name)
                where_values.append(col_value)
            else:
                upd_cols.append(col_name)
                upd_values.append(col_value)

        if _keys:
            raise ValueError('missing primary key(s): %s' % _keys)

        sql = (
            "UPDATE %s" % (self.table_name)
            + " SET "   + ", ".join(["%s=?" % c for c in upd_cols])
            + " WHERE " + " AND ".join(["%s=?" % c for c in where_cols])
        )

        return sql, upd_values + where_values

    def sql_insert_row(self, **kwargs):

        _keys = self.pkeys[:]
        _args = ("?," * len(kwargs))[:-1]

        cols = []
        values = []

        for col_name, col_value in kwargs.items():
            cols.append(col_name)
            values.append(col_value)
            if col_name in _keys:
                _keys.remove(col_name)

        if _keys:
            raise ValueError('missing primary key(s): %s' % _keys)

        sql = "INSERT INTO %s (%s) VALUES (%s);" % (self.table_name, ', '.join(cols), _args)

        return sql, values

    def init_ddl(self):

        ddl = []

        def _add(col_name, is_pkey, col_type, default):
            x = "%s %s" % (col_name, col_type)
            if is_pkey:
                self.pkeys.append(col_name)
                x += " NOT NULL"
            if default is not None:
                if col_type == 'TEXT':
                    x += " DEFAULT '%s'" % default
                else:
                    x += " DEFAULT %s" % default
            self.col_names.append(col_name)
            ddl.append(x)

        for col_name, is_pkey, col_type, default in self.col_def_list:
            _add(col_name, is_pkey, col_type, default)

        self.sql_create = "CREATE TABLE IF NOT EXISTS %s (" % self.table_name
        self.sql_create += ", ".join(ddl)
        if self.pkeys:
            self.sql_create += ", PRIMARY KEY (%s)" % ', '.join(self.pkeys)
        self.sql_create += " )"

        if self.pkeys:
            self.sql_create_idx = (
                "CREATE INDEX IF NOT EXISTS %s_index ON %s (%s)"
                % (self.table_name, self.table_name, ', '.join(self.pkeys))
            )

    def get_row(self, cur, kwargs):
        """Query a row from the DB table."""

        sql, values = self.sql_select_row(**kwargs)
        cur.execute(sql, values)
        col_names = [c[0] for c in cur.description]
        ret_val = cur.fetchone()
        if ret_val is not None:
            ret_val = dict(zip(col_names, ret_val))
        return ret_val

    def set_row(self, cur, kwargs):
        """Set a row in the DB table."""

        if self.get_row(cur, kwargs):
            sql, values = self.sql_update_row(**kwargs)
        else:
            sql, values = self.sql_insert_row(**kwargs)
        cur.execute(sql, values)
        return cur.rowcount

