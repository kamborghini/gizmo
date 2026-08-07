/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

export default async () => {
  render(<Extension />, document.body);
};

function Extension() {
  const { data } = shopify;
  const [src, setSrc] = useState(null);

  useEffect(() => {
    const ids = (data?.selected || []).map((s) => s.id);
    if (ids.length) {
      setSrc(`/print/production-labels?ids=${encodeURIComponent(ids.join(","))}`);
    }
  }, [data?.selected]);

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        <s-text>
          The production label for this order is ready. Use Print to send it to
          your label printer.
        </s-text>
      </s-stack>
    </s-admin-print-action>
  );
}