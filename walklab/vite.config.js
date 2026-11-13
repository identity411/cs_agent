import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
import {createPointStore} from './server/points.js';

const store = createPointStore(fileURLToPath(new URL('./data/start-points.json', import.meta.url)));

function pointsApi(server) {
  server.middlewares.use('/api/start-points', async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    try {
      if (req.method === 'GET') {
        const url = new URL(req.url, 'http://localhost');
        res.end(JSON.stringify(await store.list(url.searchParams.get('mapId'),
          url.searchParams.get('mapHash'))));
      } else if (req.method === 'POST') {
        let body = '';
        for await (const chunk of req) {
          body += chunk;
          if (body.length > 4096) throw new Error('request too large');
        }
        res.statusCode = 201;
        res.end(JSON.stringify(await store.add(JSON.parse(body))));
      } else if (req.method === 'PATCH') {
        let body = '';
        for await (const chunk of req) {
          body += chunk;
          if (body.length > 4096) throw new Error('request too large');
        }
        res.end(JSON.stringify(await store.update(decodeURIComponent(req.url.slice(1)),
          JSON.parse(body))));
      } else if (req.method === 'DELETE') {
        const url = new URL(req.url, 'http://localhost');
        res.end(JSON.stringify(await store.remove(decodeURIComponent(url.pathname.slice(1)),
          url.searchParams.get('mapId'), url.searchParams.get('mapHash'))));
      } else {
        res.statusCode = 405;
        res.end(JSON.stringify({error: 'method not allowed'}));
      }
    } catch (error) {
      res.statusCode = 400;
      res.end(JSON.stringify({error: error.message}));
    }
  });
}

export default defineConfig({plugins: [{name: 'walklab-points-api',
  configureServer: pointsApi, configurePreviewServer: pointsApi}]});
