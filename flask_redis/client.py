import ssl
from urllib.parse import parse_qs, unquote, urlparse

try:
    import redis
    from redis.sentinel import Sentinel
except ImportError:
    # Allow usage without redis-py being installed
    redis = None
    Sentinel = None


class FlaskRedis(object):
    def __init__(
        self,
        app=None,
        strict=True,
        config_prefix="REDIS",
        decode_responses=True,
        **kwargs,
    ):
        self._redis_client = None
        self.provider_class = redis.StrictRedis if strict else redis.Redis
        self.config_prefix = config_prefix
        self.decode_responses = decode_responses
        self.provider_kwargs = kwargs

        if app is not None:
            self.init_app(app)

    @classmethod
    def from_custom_provider(cls, provider, app=None, **kwargs):
        assert provider is not None, "Your custom provider is None."

        instance = cls(**kwargs)
        instance.provider_class = provider
        if app is not None:
            instance.init_app(app)
        return instance

    def init_app(self, app, **kwargs):
        redis_url = app.config.get(
            f"{self.config_prefix}_URL", "redis://localhost:6379/0"
        )

        self.provider_kwargs.update(kwargs)

        parsed_url = urlparse(redis_url)
        scheme = parsed_url.scheme

        if scheme in ["redis+sentinel", "rediss+sentinel"]:
            if Sentinel is None:
                raise ImportError("redis-py must be installed to use Redis Sentinel.")
            self._init_sentinel_client(parsed_url)
        else:
            self._init_standard_client(redis_url)

        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions[self.config_prefix.lower()] = self

    def _init_standard_client(self, redis_url):
        self._redis_client = self.provider_class.from_url(
            redis_url, decode_responses=self.decode_responses, **self.provider_kwargs
        )

    def _init_sentinel_client(self, parsed_url):
        sentinel_kwargs, client_kwargs = self._parse_sentinel_parameters(parsed_url)

        sentinel = Sentinel(
            sentinel_kwargs["hosts"],
            socket_timeout=sentinel_kwargs["socket_timeout"],
            **sentinel_kwargs["ssl_params"],
            **sentinel_kwargs["auth_params"],
            **self.provider_kwargs,
        )

        self._redis_client = sentinel.master_for(
            sentinel_kwargs["master_name"],
            db=client_kwargs["db"],
            socket_timeout=client_kwargs["socket_timeout"],
            decode_responses=self.decode_responses,
            **client_kwargs["ssl_params"],
            **client_kwargs["auth_params"],
            **self.provider_kwargs,
        )

    def _parse_sentinel_parameters(self, parsed_url):
        username, password = self._extract_credentials(parsed_url)
        hosts = self._parse_hosts(parsed_url)
        master_name, db = self._parse_master_and_db(parsed_url)
        query_params = parse_qs(parsed_url.query)

        socket_timeout = self._parse_socket_timeout(query_params)
        ssl_enabled = self._parse_ssl_enabled(parsed_url.scheme, query_params)
        ssl_params = self._parse_ssl_params(query_params, ssl_enabled)
        auth_params = self._parse_auth_params(username, password)

        sentinel_kwargs = {
            "hosts": hosts,
            "socket_timeout": socket_timeout,
            "ssl_params": ssl_params,
            "auth_params": auth_params,
            "master_name": master_name,
        }

        client_kwargs = {
            "db": db,
            "socket_timeout": socket_timeout,
            "ssl_params": ssl_params,
            "auth_params": auth_params,
        }

        return sentinel_kwargs, client_kwargs

    def _extract_credentials(self, parsed_url):
        username = parsed_url.username
        password = parsed_url.password
        return username, password

    def _parse_hosts(self, parsed_url):
        netloc = parsed_url.netloc
        if "@" in netloc:
            hosts_part = netloc.split("@", 1)[1]
        else:
            hosts_part = netloc

        hosts = []
        for host_port in hosts_part.split(","):
            if ":" in host_port:
                host, port = host_port.split(":", 1)
                port = int(port)
            else:
                host = host_port
                port = 26379  # Default Sentinel port
            hosts.append((host, port))
        return hosts

    def _parse_master_and_db(self, parsed_url):
        path = parsed_url.path.lstrip("/")
        if "/" in path:
            master_name, db_part = path.split("/", 1)
            db = int(db_part)
        else:
            master_name = path
            db = 0  # Default DB
        return master_name, db

    def _parse_socket_timeout(self, query_params):
        socket_timeout = query_params.get("socket_timeout", [None])[0]
        if socket_timeout is not None:
            return float(socket_timeout)
        return None

    def _parse_ssl_enabled(self, scheme, query_params):
        if scheme == "rediss+sentinel":
            return True
        ssl_param = query_params.get("ssl", ["False"])[0].lower()
        return ssl_param == "true"

    def _parse_ssl_params(self, query_params, ssl_enabled):
        ssl_params = {}
        if ssl_enabled:
            ssl_cert_reqs = self._parse_ssl_cert_reqs(query_params)
            ssl_keyfile = query_params.get("ssl_keyfile", [None])[0]
            ssl_certfile = query_params.get("ssl_certfile", [None])[0]
            ssl_ca_certs = query_params.get("ssl_ca_certs", [None])[0]

            ssl_params = {"ssl": True}
            if ssl_cert_reqs is not None:
                ssl_params["ssl_cert_reqs"] = ssl_cert_reqs
            if ssl_keyfile:
                ssl_params["ssl_keyfile"] = ssl_keyfile
            if ssl_certfile:
                ssl_params["ssl_certfile"] = ssl_certfile
            if ssl_ca_certs:
                ssl_params["ssl_ca_certs"] = ssl_ca_certs
        return ssl_params

    def _parse_ssl_cert_reqs(self, query_params):
        ssl_cert_reqs = query_params.get("ssl_cert_reqs", [None])[0]
        if ssl_cert_reqs:
            ssl_cert_reqs = ssl_cert_reqs.lower()
            return {
                "required": ssl.CERT_REQUIRED,
                "optional": ssl.CERT_OPTIONAL,
                "none": ssl.CERT_NONE,
            }.get(ssl_cert_reqs)
        return None

    def _parse_auth_params(self, username, password):
        auth_params = {}
        if username:
            auth_params["username"] = username
        if password:
            auth_params["password"] = password
        return auth_params

    def hmset(self, name, mapping):
        # Implement hmset for compatibility
        # Use hset with mapping parameter
        return self._redis_client.hset(name, mapping=mapping)

    def __getattr__(self, name):
        return getattr(self._redis_client, name)

    def __getitem__(self, name):
        return self._redis_client[name]

    def __setitem__(self, name, value):
        self._redis_client[name] = value

    def __delitem__(self, name):
        del self._redis_client[name]
