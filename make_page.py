import os
os.chdir(os.path.join(os.pardir, 'argus-web'))

# Write .env.local
with open('.env.local', 'w', encoding='utf-8') as f:
    f.write('NEXT_PUBLIC_API_URL=http://localhost:8000\n')

# Write app/page.tsx
page_content = """\"use client\";
import { useEffect, useState } from \"react\";

export default function Home() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(process.env.NEXT_PUBLIC_API_URL + \"/health\")
      .then(res => res.json())
      .then(json => setData(json))
      .catch(err => setData({ error: String(err) }));
  }, []);

  return (
    <div className=\"p-8\">
      <h1 className=\"text-2xl font-bold mb-4\">Argus Triage Dashboard</h1>
      <pre className=\"bg-gray-100 dark:bg-gray-800 p-4 rounded text-sm\">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
"""

os.makedirs('app', exist_ok=True)
with open('app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(page_content)
print('Wrote files successfully!')
