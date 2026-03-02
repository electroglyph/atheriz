from atheriz.inputfuncs import InputFuncs as BaseInputFuncs


class InputFuncs(BaseInputFuncs):
    """Custom InputFuncs class. Override methods below to customize behavior."""
    pass

# To add a custom input handler, use the @inputfunc decorator:
# from atheriz.inputfuncs import inputfunc
#
# @inputfunc()
# def my_custom_handler(self, connection, args, kwargs):
#     """Handle 'my_custom_handler' messages from client."""
#     pass
