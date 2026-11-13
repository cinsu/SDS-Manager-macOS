# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""RadioReference.com Database Web Service client (v0.1.0).

Each user signs in with their own RadioReference account, which must be a Premium subscription;
the application key identifies SDS-Manager. The service is SOAP, RPC/encoded (the WSDL at
https://api.radioreference.com/soap2/?wsdl&v=latest). This module builds the requests and reads
the replies with the standard library, and always uses HTTPS so the password is never sent in
the clear (the WSDL's address is http://).

Nothing here stores RadioReference data: replies go to the caller, which keeps only what the user
adds to their own scanner configuration.
"""
import re
import urllib.error
import urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ENDPOINT = "https://api.radioreference.com/soap2/index.php"
NS = "http://api.radioreference.com/soap2"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_ENC = "http://schemas.xmlsoap.org/soap/encoding/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
API_VERSION = "latest"
TIMEOUT = 30
MAX_REPLY = 20 * 1024 * 1024


class RRError(RuntimeError):
    """A RadioReference request failed. The text never contains the password or the key."""


def _value(name, value, xsd_type):
    if value is None:
        return f'<{name} xsi:nil="true"/>'
    return f'<{name} xsi:type="{xsd_type}">{escape(str(value))}</{name}>'


def envelope(method, params, auth):
    """The SOAP request for method(params..., authInfo). params: [(name, value, 'xsd:int'), ...]."""
    body = "".join(_value(n, v, t) for n, v, t in params)
    auth_xml = "".join(_value(k, auth.get(k, ""), "xsd:string")
                       for k in ("username", "password", "appKey", "version", "style"))
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{SOAP_ENV}" xmlns:ns1="{NS}" '
            f'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="{XSI}" xmlns:SOAP-ENC="{SOAP_ENC}" '
            f'SOAP-ENV:encodingStyle="{SOAP_ENC}"><SOAP-ENV:Body><ns1:{method}>{body}'
            f'<authInfo xsi:type="ns1:authInfo">{auth_xml}</authInfo></ns1:{method}>'
            '</SOAP-ENV:Body></SOAP-ENV:Envelope>').encode("utf-8")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _convert(node, refs):
    href = node.get("href")
    if href and href.startswith("#") and href[1:] in refs:
        node = refs[href[1:]]
    if node.get(f"{{{XSI}}}nil") in ("true", "1"):
        return None
    children = list(node)
    xsi_type = (node.get(f"{{{XSI}}}type") or "").rsplit(":", 1)[-1]
    is_array = (xsi_type == "Array" or node.get(f"{{{SOAP_ENC}}}arrayType") is not None
                or (children and all(_local(c.tag) == "item" for c in children)))
    if is_array:
        return [_convert(c, refs) for c in children]
    if children:
        return {_local(c.tag): _convert(c, refs) for c in children}
    text = (node.text or "").strip()
    if xsi_type in ("int", "integer", "long", "short") and text.lstrip("-").isdigit():
        return int(text)
    if xsi_type in ("decimal", "float", "double"):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def parse_reply(data):
    """The 'return' value of a SOAP reply, as dicts, lists and plain values. Raises RRError on a fault."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise RRError(f"RadioReference sent a reply that could not be read ({exc}).") from None
    body = next((n for n in root if _local(n.tag) == "Body"), None)
    if body is None or not len(body):
        raise RRError("RadioReference sent an empty reply.")
    first = body[0]
    if _local(first.tag) == "Fault":
        parts = {_local(c.tag): (c.text or "").strip() for c in first}
        raise RRError(parts.get("faultstring") or parts.get("faultcode") or "RadioReference refused the request.")
    refs = {n.get("id"): n for n in body.iter() if n.get("id")}
    ret = next(iter(first), None)
    return None if ret is None else _convert(ret, refs)


def post(method, data, timeout=TIMEOUT):
    """Send one request; returns the reply bytes (also for SOAP faults, which come as HTTP 500)."""
    request = urllib.request.Request(ENDPOINT, data=data, method="POST", headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}#{method}"',
        "User-Agent": "SDS-Manager"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.read(MAX_REPLY)
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_REPLY)
        if body.lstrip().startswith(b"<"):
            return body
        raise RRError(f"RadioReference answered HTTP {exc.code}.") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RRError(f"Can't reach RadioReference ({reason}).") from None


class RRClient:
    """One signed-in user. post(method, data) can be replaced for tests."""

    def __init__(self, username, password, app_key, post=post):
        if not (username and password):
            raise RRError("Enter your RadioReference username and password first.")
        if not app_key:
            raise RRError("This build of SDS-Manager has no RadioReference application key. Enter one under "
                          "Advanced in Tools → RadioReference Account…")
        self.auth = {"username": username, "password": password, "appKey": app_key,
                     "version": API_VERSION, "style": "rpc"}
        self._post = post

    def call(self, method, *params):
        data = envelope(method, params, self.auth)
        reply = self._post(method, data)
        result = parse_reply(reply)
        return result

    # -- account --
    def user_data(self):
        """{'username', 'subExpireDate'}: checks the sign-in and the Premium subscription."""
        return self.call("getUserData")

    # -- places --
    def zipcode(self, zipcode):
        """{'zipCode', 'lat', 'lon', 'city', 'stid', 'ctid'} for a US ZIP code."""
        text = str(zipcode).strip()
        if not (text.isdigit() and len(text) == 5):
            raise RRError("Enter a 5-digit US ZIP code.")
        return self.call("getZipcodeInfo", ("zipcode", int(text), "xsd:int"))

    def county(self, ctid):
        """County with its conventional categories ('cats'), trunked systems ('trsList') and agencies."""
        return self.call("getCountyInfo", ("ctid", int(ctid), "xsd:int"))

    def country(self, coid):
        """Country with its states ('stateList')."""
        return self.call("getCountryInfo", ("coid", int(coid), "xsd:int"))

    def mode(self, mode):
        """[{'mode', 'modeName'}] for a mode number."""
        return self.call("getMode", ("mode", int(mode), "xsd:int"))

    def trs_type(self, type_id):
        """[{'sType', 'sTypeDescr'}] for a trunked system type number."""
        return self.call("getTrsType", ("id", int(type_id), "xsd:int"))

    def state(self, stid):
        return self.call("getStateInfo", ("stid", int(stid), "xsd:int"))

    def agency(self, aid):
        return self.call("getAgencyInfo", ("aid", int(aid), "xsd:int"))

    # -- conventional --
    def subcat_freqs(self, scid):
        return self.call("getSubcatFreqs", ("scid", int(scid), "xsd:int"))

    def county_freqs_by_tag(self, ctid, tag):
        return self.call("getCountyFreqsByTag", ("ctid", int(ctid), "xsd:int"), ("tag", int(tag), "xsd:int"))

    def search_county_freq(self, ctid, mhz, tone=""):
        return self.call("searchCountyFreq", ("ctid", int(ctid), "xsd:int"), ("freq", f"{float(mhz):.5f}", "xsd:decimal"),
                         ("tone", tone, "xsd:string"))

    def search_state_freq(self, stid, mhz, tone=""):
        """Conventional frequencies across a state (v0.1.28)."""
        return self.call("searchStateFreq", ("stid", int(stid), "xsd:int"), ("freq", f"{float(mhz):.5f}", "xsd:decimal"),
                         ("tone", tone, "xsd:string"))

    # -- trunked --
    def trs_details(self, sid):
        return self.call("getTrsDetails", ("sid", int(sid), "xsd:int"))

    def trs_sites(self, sid):
        return self.call("getTrsSites", ("sid", int(sid), "xsd:int"))

    def trs_talkgroup_cats(self, sid):
        return self.call("getTrsTalkgroupCats", ("sid", int(sid), "xsd:int"))

    def trs_talkgroups(self, sid, category=0, tag=0, decimal=0):
        """Talkgroups of a system; 0 means 'all' for category, tag and decimal ID."""
        return self.call("getTrsTalkgroups", ("sid", int(sid), "xsd:int"), ("tgCid", int(category), "xsd:int"),
                         ("tgTag", int(tag), "xsd:int"), ("tgDec", int(decimal), "xsd:int"))

    def trs_by_sysid(self, sysid):
        return self.call("getTrsBySysid", ("sysid", str(sysid), "xsd:string"))


# ---- the application key (v0.1.4) ---------------------------------------------------------------
# The key identifies SDS-Manager to RadioReference; users sign in with their own account. It is not in
# the source: add_rr_key.sh puts it into a package as /opt/sds-manager/rr_app_key. A build without one
# (someone building from source) uses the key its user enters under Advanced.
KEY_FILES = (Path(__file__).resolve().with_name("rr_app_key"), Path("/etc/sds-manager/rr_app_key"))


def read_key(path):
    try:
        text = Path(path).read_text(encoding="ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return ""
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{4,128}", text) else ""


def bundled_app_key(paths=None):
    """The application key that came with this installation, or ''."""
    for path in paths or KEY_FILES:
        key = read_key(path)
        if key:
            return key
    return ""


# ---- the user's account details -----------------------------------------------------------------
KEYRING_SERVICE = "SDS-Manager RadioReference"


def keyring_backend():
    """The keyring module if a real secret store (KDE Wallet, GNOME Keyring) is available, else None."""
    try:
        import keyring
        from keyring.backends import fail
    except Exception:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    if isinstance(backend, fail.Keyring) or "null" in type(backend).__module__.lower():
        return None
    return keyring


class Account:
    """Username (in the settings file) and password and application key (in the secret store only).
    Without a secret store, the password and key are kept for this session only."""

    def __init__(self, settings, secrets="auto", bundled=None):
        self.settings = settings                # QSettings-like: value(key, default), setValue(key, value)
        self.secrets = keyring_backend() if secrets == "auto" else secrets
        self.session = {}
        self.bundled_key = bundled_app_key() if bundled is None else bundled

    def app_key(self):
        """The package's key; the user's own key only when the package has none."""
        return self.bundled_key or self.secret("appKey")

    def username(self):
        return str(self.settings.value("radioreference/username", "") or "")

    def secret(self, name):
        if name in self.session:
            return self.session[name]
        if self.secrets is not None and self.username():
            try:
                return self.secrets.get_password(KEYRING_SERVICE, f"{name}:{self.username()}") or ""
            except Exception:
                return ""
        return ""

    def save(self, username, password, app_key="", remember=True):
        """Returns True if the password (and a user's own key) were kept in the secret store."""
        old = self.username()
        self.settings.setValue("radioreference/username", username.strip())
        self.session = {"password": password, "appKey": app_key.strip()}
        if not (remember and self.secrets is not None):
            self.forget_stored(old)
            return False
        try:
            if old and old != username.strip():
                self.forget_stored(old)
            self.secrets.set_password(KEYRING_SERVICE, f"password:{username.strip()}", password)
            if app_key.strip():
                self.secrets.set_password(KEYRING_SERVICE, f"appKey:{username.strip()}", app_key.strip())
            else:
                try:
                    self.secrets.delete_password(KEYRING_SERVICE, f"appKey:{username.strip()}")
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def forget_stored(self, username=None):
        username = username or self.username()
        if self.secrets is None or not username:
            return
        for name in ("password", "appKey"):
            try:
                self.secrets.delete_password(KEYRING_SERVICE, f"{name}:{username}")
            except Exception:
                pass

    def client(self, post=post):
        return RRClient(self.username(), self.secret("password"), self.app_key(), post=post)
