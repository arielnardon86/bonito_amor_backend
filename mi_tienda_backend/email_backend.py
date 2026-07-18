import ssl

import certifi
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend
from django.utils.functional import cached_property


class EmailBackend(DjangoSMTPEmailBackend):
    """
    Backend SMTP idéntico al de Django, salvo que arma el contexto SSL con el
    bundle de certificados de certifi en vez del truststore del sistema
    operativo. En macOS con Python instalado desde python.org (no Homebrew)
    ese truststore no está enlazado y el envío falla con
    CERTIFICATE_VERIFY_FAILED; certifi funciona igual en cualquier SO,
    incluyendo el entorno de producción (Render).
    """

    @cached_property
    def ssl_context(self):
        if self.ssl_certfile or self.ssl_keyfile:
            return super().ssl_context
        return ssl.create_default_context(cafile=certifi.where())
