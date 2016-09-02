import sys
import logging
import structlog
import importlib
import base64
import binascii
import pytz

from datetime import datetime


from .exceptions import InvalidAuthHeader

log = structlog.getLogger(__name__)


def import_class(module_class_name):
    module_name, _, class_name = module_class_name.rpartition('.')
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def load_inner_api(api_config):
    class_name = api_config['class']
    cls = import_class(class_name)
    params = api_config.get('parameters', None)

    if params:
        instance = cls(**params)
    else:
        instance = cls()

    log.info("inner-api.loaded", api=class_name)

    return instance


def parse_basic_auth_token(token):
    print("'{}'".format(token), len(token))
    try:
        value = base64.b64decode(token)
    except (TypeError, binascii.Error):
        raise InvalidAuthHeader("Can't decode Basic Auth header value")

    try:
        value = value.decode('utf-8')
        username, password = value.split(':', 1)
        return (username, password)
    except ValueError:
        raise InvalidAuthHeader("Invalid Basic Auth header value")


class PlainRenderer(object):

    def __call__(self, logger, name, event_dict):

        logger = event_dict.pop('logger')
        level = event_dict.pop('level')
        event = event_dict.pop('event')
        timestamp = event_dict.pop('timestamp')

        pairs = ', '.join(['%s=%s' % (k, v) for k, v in event_dict.items()])
        return (
            '{timestamp} [{logger}] {level}: {event} {{{pairs}}}'
            .format(timestamp=timestamp, logger=logger, level=level,
                    event=event, pairs=pairs))


def configure_logging(logging_levels, plain=False):

    _remove_all_existing_log_handlers()

    renderer = (
        PlainRenderer() if plain else
        structlog.processors.JSONRenderer())

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    for logger, level in logging_levels.items():

        if logger.lower() == 'root':
            logger = ''

        logging.getLogger(logger).setLevel(level.upper())


def _remove_all_existing_log_handlers():
    for logger in logging.Logger.manager.loggerDict.values():
        if hasattr(logger, 'handlers'):
            del logger.handlers[:]

    root_logger = logging.getLogger()
    del root_logger.handlers[:]


def get_utc_now():
    return datetime.utcnow().replace(tzinfo=pytz.UTC)


def is_content_supported(supported_bindings, content_binding, version=None):

    if not hasattr(content_binding, 'binding_id') or version == 10:
        binding_id = content_binding
        subtype = None
    else:
        binding_id = content_binding.binding_id

        # FIXME: may be not the best option
        subtype = (
            content_binding.subtype_ids[0] if content_binding.subtype_ids
            else None)

    matches = [
        ((supported.binding == binding_id) and
         (not supported.subtypes or subtype in supported.subtypes))
        for supported in supported_bindings
    ]

    return any(matches)
