import os
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
        self.client = None

    def get_client(self):
        if not self.client:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=60,
                send_receive_timeout=self.timeout,
                settings={'max_execution_time': self.timeout}
            )
        return self.client

    def query_df(self, query, parameters=None, settings=None):
        client = self.get_client()
        return client.query_df(query, parameters=parameters, settings=settings)

    def command(self, cmd, parameters=None, settings=None):
        client = self.get_client()
        return client.command(cmd, parameters=parameters, settings=settings)

    def query(self, query, parameters=None, settings=None):
        client = self.get_client()
        return client.query(query, parameters=parameters, settings=settings)

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

# Singleton instance
ch_client = ClickHouseClient()
