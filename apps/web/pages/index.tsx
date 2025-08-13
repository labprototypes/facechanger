export default function Home(){
  return (
    <div className="min-h-screen p-6">
      <h1 className="text-2xl font-semibold mb-4">facechanger</h1>
      <ul className="list-disc pl-6">
        <li><a className="underline" href="/upload">Загрузка по SKU</a></li>
        <li><a className="underline" href="/dashboard">Dashboard</a></li>
      </ul>
    </div>
  );
}
