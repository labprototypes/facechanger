import { useRouter } from "next/router";
import SkuCard from "../../components/SkuCard";

export default function SkuPage() {
  const { query } = useRouter();
  const sku = String(query.sku || "DEMO-SKU");

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <SkuCard sku={sku} />
    </div>
  );
}
