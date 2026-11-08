# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""RadioReference client (v0.1.0): requests, replies, faults and where the password and key are kept.
v0.1.4: the application key built into a package."""
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rr_api

HEAD = ('<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:ns1="http://api.radioreference.com/soap2" xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/" '
        'SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><SOAP-ENV:Body>')
TAIL = '</SOAP-ENV:Body></SOAP-ENV:Envelope>'
USER = (HEAD + '<ns1:getUserDataResponse><return xsi:type="ns1:UserInfo"><username xsi:type="xsd:string">listener</username>'
        '<subExpireDate xsi:type="xsd:string">2027-03-01</subExpireDate></return></ns1:getUserDataResponse>' + TAIL)
TALKGROUPS = (HEAD + '<ns1:getTrsTalkgroupsResponse><return SOAP-ENC:arrayType="ns1:Talkgroup[2]" xsi:type="ns1:Talkgroups">'
              '<item xsi:type="ns1:Talkgroup"><tgId xsi:type="xsd:int">101</tgId><tgDec xsi:type="xsd:int">44358</tgDec>'
              '<tgAlpha xsi:type="xsd:string">GVL PD Disp</tgAlpha><tgDescr xsi:type="xsd:string">Police Dispatch</tgDescr>'
              '<tgMode xsi:type="xsd:string">D</tgMode><enc xsi:type="xsd:int">0</enc>'
              '<tags SOAP-ENC:arrayType="ns1:tag[1]" xsi:type="ns1:tags"><item xsi:type="ns1:tag">'
              '<tagId xsi:type="xsd:int">2</tagId><tagDescr xsi:type="xsd:string">Law Dispatch</tagDescr></item></tags>'
              '<tgCid xsi:type="xsd:int">7</tgCid></item>'
              '<item xsi:type="ns1:Talkgroup"><tgId xsi:type="xsd:int">102</tgId><tgDec xsi:type="xsd:int">44356</tgDec>'
              '<tgAlpha xsi:type="xsd:string">GVL PD Traf</tgAlpha><tgDescr xsi:type="xsd:string">Traffic &amp; Ops</tgDescr>'
              '<tgMode xsi:type="xsd:string">DE</tgMode><enc xsi:type="xsd:int">2</enc>'
              '<tags SOAP-ENC:arrayType="ns1:tag[0]" xsi:type="ns1:tags"/><tgCid xsi:type="xsd:int">7</tgCid></item>'
              '</return></ns1:getTrsTalkgroupsResponse>' + TAIL)
ZIP = (HEAD + '<ns1:getZipcodeInfoResponse><return xsi:type="ns1:ZipInfo"><zipCode xsi:type="xsd:int">29601</zipCode>'
       '<lat xsi:type="xsd:decimal">34.847</lat><lon xsi:type="xsd:decimal">-82.400</lon>'
       '<city xsi:type="xsd:string">Greenville</city><stid xsi:type="xsd:int">45</stid>'
       '<ctid xsi:type="xsd:int">2345</ctid></return></ns1:getZipcodeInfoResponse>' + TAIL)
FAULT = (HEAD + '<SOAP-ENV:Fault><faultcode>AUTH</faultcode><faultstring>Invalid user credentials</faultstring>'
         '</SOAP-ENV:Fault>' + TAIL)


class FakeSecrets:
    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        self.store.pop((service, name), None)


class Settings(dict):
    def value(self, key, default=None):
        return self.get(key, default)

    def setValue(self, key, value):
        self[key] = value


class RRApiTests(unittest.TestCase):
    def client(self, reply):
        self.sent = []

        def post(method, data):
            self.sent.append((method, data))
            if isinstance(reply, Exception):
                raise reply
            return reply.encode()
        return rr_api.RRClient('listener', 'pa<ss&word', 'APPKEY', post=post)

    def test_request_is_rpc_encoded_with_auth(self):
        c = self.client(TALKGROUPS)
        c.trs_talkgroups(6060)
        method, data = self.sent[0]
        self.assertEqual(method, 'getTrsTalkgroups')
        root = ET.fromstring(data)
        call = root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')[0]
        self.assertEqual(call.tag, '{http://api.radioreference.com/soap2}getTrsTalkgroups')
        self.assertEqual([c.tag for c in call], ['sid', 'tgCid', 'tgTag', 'tgDec', 'authInfo'])
        self.assertEqual(call.find('sid').text, '6060')
        auth = {c.tag: c.text for c in call.find('authInfo')}
        self.assertEqual(auth, {'username': 'listener', 'password': 'pa<ss&word', 'appKey': 'APPKEY',
                                'version': 'latest', 'style': 'rpc'})

    def test_reply_values_and_arrays(self):
        self.assertEqual(self.client(USER).user_data(), {'username': 'listener', 'subExpireDate': '2027-03-01'})
        tgs = self.client(TALKGROUPS).trs_talkgroups(6060)
        self.assertEqual([t['tgDec'] for t in tgs], [44358, 44356])
        self.assertEqual(tgs[0]['tags'], [{'tagId': 2, 'tagDescr': 'Law Dispatch'}])
        self.assertEqual(tgs[1]['tags'], [])
        self.assertEqual(tgs[1]['tgDescr'], 'Traffic & Ops')
        z = self.client(ZIP).zipcode('29601')
        self.assertEqual((z['ctid'], z['lat']), (2345, 34.847))

    def test_fault_is_an_error_without_secrets(self):
        with self.assertRaises(rr_api.RRError) as cm:
            self.client(FAULT).user_data()
        self.assertEqual(str(cm.exception), 'Invalid user credentials')
        with self.assertRaises(rr_api.RRError) as cm:
            self.client('not xml').user_data()
        self.assertNotIn('pa<ss&word', str(cm.exception))
        self.assertNotIn('APPKEY', str(cm.exception))

    def test_bad_input_is_refused_before_sending(self):
        c = self.client(ZIP)
        for bad in ('2960', 'abcde', '296011'):
            with self.assertRaises(rr_api.RRError):
                c.zipcode(bad)
        self.assertEqual(self.sent, [])
        with self.assertRaises(rr_api.RRError):
            rr_api.RRClient('listener', '', 'APPKEY')

    def test_always_https(self):
        self.assertTrue(rr_api.ENDPOINT.startswith('https://'))

    def test_account_keeps_secrets_out_of_settings(self):
        settings, secrets = Settings(), FakeSecrets()
        account = rr_api.Account(settings, secrets=secrets, bundled='')
        self.assertTrue(account.save('listener', 'pw', 'KEY'))
        self.assertEqual(settings, {'radioreference/username': 'listener'})
        fresh = rr_api.Account(settings, secrets=secrets, bundled='')
        self.assertEqual((fresh.secret('password'), fresh.secret('appKey')), ('pw', 'KEY'))
        fresh.forget_stored()
        self.assertEqual(secrets.store, {})

    def test_without_a_secret_store_the_session_only(self):
        settings = Settings()
        account = rr_api.Account(settings, secrets=None, bundled='')
        self.assertFalse(account.save('listener', 'pw', 'KEY'))
        self.assertEqual(account.secret('password'), 'pw')
        self.assertEqual(settings, {'radioreference/username': 'listener'})
        self.assertEqual(rr_api.Account(settings, secrets=None).secret('password'), '')

    def test_the_bundled_key_comes_first(self):
        settings, secrets = Settings(), FakeSecrets()
        account = rr_api.Account(settings, secrets=secrets, bundled='PACKAGEKEY')
        self.assertTrue(account.save('listener', 'pw'))                    # no key asked for
        self.assertEqual(secrets.store, {(rr_api.KEYRING_SERVICE, 'password:listener'): 'pw'})
        sent = []
        account.client(post=lambda m, data: sent.append(data) or USER.encode()).user_data()
        self.assertIn(b'<appKey xsi:type="xsd:string">PACKAGEKEY</appKey>', sent[0])
        # an older user key in the wallet is ignored while the package has one, and removed on save
        secrets.store[(rr_api.KEYRING_SERVICE, 'appKey:listener')] = 'OLD'
        self.assertEqual(account.app_key(), 'PACKAGEKEY')
        account.save('listener', 'pw')
        self.assertNotIn((rr_api.KEYRING_SERVICE, 'appKey:listener'), secrets.store)

    def test_without_a_bundled_key_the_users_own(self):
        settings, secrets = Settings(), FakeSecrets()
        account = rr_api.Account(settings, secrets=secrets, bundled='')
        account.save('listener', 'pw', 'MINE')
        self.assertEqual(rr_api.Account(settings, secrets=secrets, bundled='').app_key(), 'MINE')
        account.save('listener', 'pw', '')
        with self.assertRaises(rr_api.RRError) as cm:
            rr_api.Account(settings, secrets=secrets, bundled='').client()
        self.assertIn('Advanced', str(cm.exception))

    def test_key_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad, missing = (rr_api.Path(tmp) / n for n in ('good', 'bad', 'missing'))
            good.write_text('  abc-123_XYZ\n')
            bad.write_text('two words\n')
            self.assertEqual(rr_api.read_key(good), 'abc-123_XYZ')
            self.assertEqual(rr_api.read_key(bad), '')
            self.assertEqual(rr_api.bundled_app_key([missing, bad, good]), 'abc-123_XYZ')
            self.assertEqual(rr_api.bundled_app_key([missing, bad]), '')
        self.assertEqual(rr_api.KEY_FILES[0].name, 'rr_app_key')

    def test_a_real_http_exchange(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.headers['SOAPAction'], self.rfile.read(int(self.headers['Content-Length']))))
                body = FAULT.encode() if b'wrong' in seen[-1][1] else USER.encode()
                self.send_response(500 if b'wrong' in seen[-1][1] else 200)
                self.send_header('Content-Type', 'text/xml')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        old = rr_api.ENDPOINT
        rr_api.ENDPOINT = f'http://127.0.0.1:{server.server_port}/soap2/index.php'
        try:
            self.assertEqual(rr_api.RRClient('listener', 'pw', 'K').user_data()['username'], 'listener')
            with self.assertRaises(rr_api.RRError) as cm:
                rr_api.RRClient('listener', 'wrong', 'K').user_data()       # SOAP faults come as HTTP 500
            self.assertEqual(str(cm.exception), 'Invalid user credentials')
        finally:
            rr_api.ENDPOINT = old
            server.shutdown()
            server.server_close()
        self.assertEqual(seen[0][0], '"http://api.radioreference.com/soap2#getUserData"')


class RRAccountDialogTests(unittest.TestCase):
    def test_dialog_saves_and_reports(self):
        import qt_stub
        with qt_stub.installed(forget=('rr_account_dialog',)):
            import rr_account_dialog as d
            from unittest.mock import MagicMock
            d.RRAccountDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
            settings, secrets = Settings(), FakeSecrets()
            account = rr_api.Account(settings, secrets=secrets, bundled='')

            class Main:
                def _run_background(self, title, text, work, done):
                    try:
                        done(work(), None)
                    except rr_api.RRError as exc:
                        done(None, str(exc))
            dialog = d.RRAccountDialog(Main(), account=account)
            dialog.username.text.return_value = 'listener'
            dialog.password.text.return_value = 'pw'
            dialog.app_key.text.return_value = 'KEY'
            dialog.remember.isChecked.return_value = True
            replies = []
            account.client = lambda: rr_api.RRClient('listener', 'pw', 'KEY', post=lambda m, data: USER.encode())
            dialog.status_label.setText.side_effect = replies.append
            dialog.save_and_test()
            self.assertIn('Signed in as <b>listener</b>', replies[-1])
            self.assertIn('2027-03-01', replies[-1])
            self.assertEqual(settings, {'radioreference/username': 'listener'})
            self.assertEqual(secrets.store[(rr_api.KEYRING_SERVICE, 'password:listener')], 'pw')
            account.client = lambda: rr_api.RRClient('listener', 'pw', 'KEY', post=lambda m, data: FAULT.encode())
            dialog.save_and_test()
            self.assertIn('Invalid user credentials', replies[-1])
            dialog.forget()
            self.assertEqual(secrets.store, {})

    def test_with_a_bundled_key_only_username_and_password(self):
        import qt_stub
        with qt_stub.installed(forget=('rr_account_dialog',)):
            import rr_account_dialog as d
            from unittest.mock import MagicMock
            d.RRAccountDialog._get_child_mock = lambda _self, **kw: MagicMock(**kw)
            settings, secrets = Settings(), FakeSecrets()
            account = rr_api.Account(settings, secrets=secrets, bundled='PACKAGEKEY')
            dialog = d.RRAccountDialog(None, account=account)
            self.assertTrue(dialog.bundled)
            dialog.app_key.setVisible.assert_called_with(False)
            dialog.username.text.return_value = 'listener'
            dialog.password.text.return_value = 'pw'
            dialog.app_key.text.return_value = 'TYPED'                   # hidden; never used
            dialog.remember.isChecked.return_value = True
            dialog.save()
            self.assertEqual(secrets.store, {(rr_api.KEYRING_SERVICE, 'password:listener'): 'pw'})
            self.assertEqual(account.app_key(), 'PACKAGEKEY')


if __name__ == '__main__':
    unittest.main()
