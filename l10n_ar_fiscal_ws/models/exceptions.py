import yaml
import sys
from zeep.helpers import serialize_object


class ArcaError(Exception):
    """Generic error managed by the client.

    Typically when the user tries to do something that has no sense given the current
    state of a record.
    """

    http_status = 400  # Unprocessable Entity

    def __init__(self, message):
        """
        :param message: exception message and frontend modal content
        """

        if message and str(type(message)).startswith("<class 'zeep.objects"):
            message = yaml.safe_dump(
                serialize_object(message, target_cls=dict),
                default_flow_style=False,
                allow_unicode=True,
            )
        super().__init__(message)
