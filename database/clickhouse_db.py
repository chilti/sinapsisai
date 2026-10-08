import os
import threading
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

class ClickHouseClient:
    def __init__(self, host=None, port=None, user=None, password=None, database=None, timeout=None):
        self.host = host or os.getenv('CH_HOST', 'localhost')
        self.port = int(port or os.getenv('CH_PORT', 8123))
        self.user = user or os.getenv('CH_USER', 'default')
        self.password = password or os.getenv('CH_PASSWORD', '')
        self.database = database or os.getenv('CH_DATABASE', 'default')
        self.timeout = int(timeout or os.getenv('CH_TIMEOUT', 1800))
        self._local = threading.local()

    def get_client(self):
        client = getattr(self._local, 'client', None)
        if client is None:
            client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=60,
                send_receive_timeout=self.timeout,
                settings={'max_execution_time': self.timeout}
            )
            self._local.client = client
        return client

    def query_df(self, query, parameters=None, settings=None):
        return self.get_client().query_df(query, parameters=parameters, settings=settings)

    def command(self, cmd, parameters=None, settings=None):
        return self.get_client().command(cmd, parameters=parameters, settings=settings)

    def query(self, query, parameters=None, settings=None):
        return self.get_client().query(query, parameters=parameters, settings=settings)

    def insert_df(self, table, df, database=None, settings=None):
        return self.get_client().insert_df(table=table, df=df, database=database, settings=settings)

    def close(self):
        client = getattr(self._local, 'client', None)
        if client:
            client.close()
            self._local.client = None

# Singleton instance
ch_client = ClickHouseClient()

