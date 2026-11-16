from drf_spectacular.extensions import OpenApiAuthenticationExtension
from admin_panel.authentication import BcryptJWTAuthentication

class BcryptJWTScheme(OpenApiAuthenticationExtension):
    target_class = BcryptJWTAuthentication
    name = 'jwtAuth'
    match_subclasses = True

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
