"""
Implementación mínima del servicio AFIP/ARCA "Consulta a Padrón - Alcance 13"
(ws_sr_padron_a13). No viene incluido en pyafipws -- esa librería solo trae
A4 y A5 (pyafipws.ws_sr_padron.WSSrPadronA4/A5) -- así que se escribe acá
siguiendo el mismo patrón que WSSrPadronA4 (subclase de BaseWS, mismo flujo
Conectar/SetTicketAcceso/Consultar vía inicializar_y_capturar_excepciones).

Se eligió A13 en vez de A4/A5 porque, en la práctica, el Administrador de
Relaciones de Clave Fiscal de AFIP no ofrece "WS SR PADRON A5" como servicio
autorizable para la gran mayoría de las cuentas, y en el caso que motivó este
código tampoco dejó adherir a A4 -- solo A13 estaba disponible para adherir.

Los nombres de campo y el service ID vienen del manual oficial de AFIP
"Manual Consulta a Padrón – Alcance 13 – V.1.4" (ws_sr_padron_a13):
  - Service ID (WSAA): ws_sr_padron_a13
  - WSDL homologación: https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13?wsdl
  - WSDL producción:   https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?wsdl
  - Método SOAP: getPersona(token, sign, cuitRepresentada, idPersona) ->
    personaReturn.persona, con: nombre, apellido, razonSocial, tipoPersona,
    estadoClave, domicilio[] (direccion, localidad, descripcionProvincia,
    codigoPostal, tipoDomicilio: FISCAL | LEGAL/REAL).

A diferencia de A4/A5, el padrón A13 NO incluye impuestos/categorías/condición
IVA -- es un servicio de identidad + domicilio solamente (confirmado contra
el esquema XSD del WSDL y el manual oficial, sección "Tipo Persona"). Por eso
este cliente no expone cat_iva: cualquier código que lo use debe dejar la
condición IVA para que la complete el usuario a mano.
"""
from pyafipws.utils import BaseWS, inicializar_y_capturar_excepciones

WSDL = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13?wsdl"


class WSSrPadronA13(BaseWS):
    "Interfaz para el WebService de Consulta Padrón Contribuyentes Alcance 13"

    _public_methods_ = ["Consultar", "Conectar", "SetTicketAcceso", "DebugLog"]
    _public_attrs_ = [
        "Token", "Sign", "Cuit",
        "XmlRequest", "XmlResponse",
        "LanzarExcepciones", "Excepcion", "Traceback",
        "denominacion", "direccion", "localidad", "provincia", "cod_postal",
        "tipo_persona", "estado", "domicilios", "data",
    ]
    WSDL = WSDL

    def inicializar(self):
        BaseWS.inicializar(self)
        self.denominacion = ""
        self.direccion = self.localidad = self.provincia = self.cod_postal = ""
        self.tipo_persona = self.estado = ""
        self.domicilios = []
        self.data = {}

    @inicializar_y_capturar_excepciones
    def Consultar(self, id_persona):
        "Devuelve denominación y domicilio de la persona solicitada (sin condición IVA: A13 no la provee)."
        res = self.client.getPersona(
            sign=self.Sign,
            token=self.Token,
            cuitRepresentada=self.Cuit,
            idPersona=id_persona,
        )
        ret = res.get("personaReturn", {})
        data = ret.get("persona", None)
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return False
        self.data = data

        self.tipo_persona = data.get("tipoPersona", "")
        self.estado = data.get("estadoClave", "")

        razon_social = data.get("razonSocial")
        if razon_social:
            self.denominacion = razon_social
        else:
            self.denominacion = ", ".join(
                filter(None, [data.get("apellido", ""), data.get("nombre", "")])
            )

        domicilios = data.get("domicilio", [])
        if isinstance(domicilios, dict):
            domicilios = [domicilios]
        # Preferir el domicilio FISCAL sobre LEGAL/REAL, mismo criterio que
        # usa pyafipws.WSSrPadronA4.Consultar para su propia lista de domicilios.
        domicilios = sorted(domicilios, key=lambda d: d.get("tipoDomicilio") != "FISCAL")
        self.domicilios = domicilios
        if domicilios:
            dom = domicilios[0]
            self.direccion = dom.get("direccion", "")
            self.localidad = dom.get("localidad", "")
            self.provincia = dom.get("descripcionProvincia", "")
            self.cod_postal = dom.get("codigoPostal", "")
        else:
            self.direccion = self.localidad = self.provincia = self.cod_postal = ""

        return True
