1. Copy the downloaded q-vercel-latency.json into the api/ folder (next to index.py).
2. git init && git add . && git commit -m "latency endpoint"
3. npx vercel --prod
4. In Vercel dashboard: Project > Settings > Deployment Protection > Vercel Authentication = Disabled
5. Submit:  https://<your-project>.vercel.app/api/latency
