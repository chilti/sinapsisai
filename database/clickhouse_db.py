import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

class ClickHouseClient:
    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        self.host = host or os.getenv('CH_HOST', 'localhost')
        self.port = int(port or os.getenv('CH_PORT', 8123))
        self.user = user or os.getenv('CH_USER', 'default')
        self.password = password or os.getenv('CH_PASSWORD', '')
        self.database = database or os.getenv('CH_DATABASE', 'default')
        self.client = None

    def get_client(self):
        if not self.client:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database
            )
        return self.client

    def query_df(self, query, parameters=None):
        client = self.get_client()
        return client.query_df(query, parameters=parameters)

    def command(self, cmd, parameters=None):
        client = self.get_client()
        return client.command(cmd, parameters=parameters)

    def query(self, query, parameters=None):
        client = self.get_client()
        return client.query(query, parameters=parameters)

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

# Singleton instance
ch_client = ClickHouseClient()
