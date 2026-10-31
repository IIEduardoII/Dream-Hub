import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app import create_app


class HttpsDuckDnsAndPwaTestCase(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.upload_dir = tempfile.mkdtemp(prefix='dreamhub_pwa_test_')
        self.app = create_app({
            'TESTING': True,
            'DATABASE': self.db_path,
            'UPLOAD_FOLDER': self.upload_dir
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        for ext in ('-wal', '-shm'):
            p = f"{self.db_path}{ext}"
            if os.path.exists(p):
                os.unlink(p)
        if os.path.exists(self.upload_dir):
            shutil.rmtree(self.upload_dir, ignore_errors=True)

    def test_rn01_git_anonymization_and_env_template(self):
        with open(os.path.join(self.project_root, '.gitignore'), 'r', encoding='utf-8') as f:
            gitignore = f.read()
        self.assertIn('.env', gitignore)
        self.assertIn('certs/', gitignore)

        env_example_path = os.path.join(self.project_root, '.env.example')
        self.assertTrue(os.path.exists(env_example_path))
        with open(env_example_path, 'r', encoding='utf-8') as f:
            env_example = f.read()
        self.assertIn('DUCKDNS_DOMAIN=', env_example)
        self.assertIn('DUCKDNS_TOKEN=', env_example)
        self.assertNotIn('lsblk', env_example)

    def test_rf02_rf03_rnf01_rnf02_nginx_and_https_scripts(self):
        with open(os.path.join(self.project_root, 'nginx-nexus.conf'), 'r', encoding='utf-8') as f:
            nginx_conf = f.read()
        self.assertIn('listen 0.0.0.0:8445 ssl;', nginx_conf)
        self.assertIn('__DUCKDNS_DOMAIN__', nginx_conf)
        self.assertIn('allow 100.64.0.0/10;', nginx_conf)
        self.assertIn('deny all;', nginx_conf)
        self.assertIn('/nexus-termux/certs/server.crt;', nginx_conf)
        self.assertIn('TLSv1.2 TLSv1.3', nginx_conf)

        setup_script = os.path.join(self.project_root, 'scripts', 'setup-https-duckdns.sh')
        deploy_script = os.path.join(self.project_root, 'scripts', 'deploy-to-termux.sh')
        self.assertTrue(os.path.exists(setup_script))
        self.assertTrue(os.access(setup_script, os.X_OK))

        with open(setup_script, 'r', encoding='utf-8') as f:
            setup_content = f.read()
        self.assertIn('dns_duckdns', setup_content)
        self.assertIn('letsencrypt', setup_content)
        self.assertIn('ec-256', setup_content)

        with open(deploy_script, 'r', encoding='utf-8') as f:
            deploy_content = f.read()
        self.assertIn('Preservando certificado TLS existente', deploy_content)
        self.assertNotIn('PHONE_PASS="lsblk"', deploy_content)

        for script in (setup_script, deploy_script):
            res = subprocess.run(['bash', '-n', script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_pwa_webapk_manifest_and_png_icons(self):
        res = self.client.get('/manifest.webmanifest')
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/manifest+json', res.headers.get('Content-Type', ''))

        manifest = json.loads(res.data.decode('utf-8'))
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['background_color'], '#000000')
        self.assertEqual(manifest['theme_color'], '#000000')
        self.assertEqual(manifest['start_url'], '/')
        self.assertEqual(manifest['scope'], '/')
        self.assertGreaterEqual(len(manifest.get('shortcuts', [])), 4)

        purposes = {(i['sizes'], i['type'], i['purpose']) for i in manifest['icons']}
        self.assertIn(('192x192', 'image/png', 'any'), purposes)
        self.assertIn(('512x512', 'image/png', 'any'), purposes)
        self.assertIn(('512x512', 'image/png', 'maskable'), purposes)

        for icon_path in (
            '/icons/icon-192.png',
            '/icons/icon-512.png',
            '/icons/icon-maskable-512.png',
            '/icons/apple-touch-icon.png'
        ):
            icon_res = self.client.get(icon_path)
            self.assertEqual(icon_res.status_code, 200, f"Missing icon {icon_path}")
            self.assertTrue(icon_res.data.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_pwa_service_worker_and_frontend_syntax(self):
        sw_res = self.client.get('/sw.js')
        self.assertEqual(sw_res.status_code, 200)
        self.assertEqual(sw_res.headers.get('Service-Worker-Allowed'), '/')
        self.assertIn('no-store', sw_res.headers.get('Cache-Control', ''))
        sw_text = sw_res.data.decode('utf-8')
        self.assertIn("self.addEventListener('fetch'", sw_text)
        self.assertNotIn('syncOfflineQueue', sw_text)

        html_res = self.client.get('/')
        self.assertEqual(html_res.status_code, 200)
        html_text = html_res.data.decode('utf-8')
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', html_text)
        self.assertIn('id="btn-install-pwa"', html_text)
        self.assertIn('/icons/apple-touch-icon.png', html_text)

        if shutil.which('node'):
            for js_rel in ('frontend/js/app.js', 'frontend/sw.js'):
                js_path = os.path.join(self.project_root, js_rel)
                chk = subprocess.run(['node', '--check', js_path], capture_output=True, text=True)
                self.assertEqual(chk.returncode, 0, msg=chk.stderr)


if __name__ == '__main__':
    unittest.main()
