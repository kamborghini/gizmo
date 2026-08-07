/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

export default async () => {
  render(<Extension />, document.body);
};

function Extension() {
  const { data } = shopify;
  const [baseUrl, setBaseUrl] = useState(null);
  const [portrait, setPortrait] = useState(false);
  const [status, setStatus] = useState("starting");

  useEffect(() => {
    const sel = (data && data.selected) || [];
    const ids = sel.map((s) => s && s.id).filter(Boolean);
    if (!ids.length) { setStatus("no order was passed to this action"); return; }
    setStatus("preparing " + ids.length + " label(s)");
    (async () => {
      try {
        const res = await fetch("/print/production-labels/sign", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: ids.join(",") }),
        });
        if (!res.ok) { setStatus("label service responded " + res.status); return; }
        const out = await res.json();
        if (!out.url) { setStatus("no document URL returned"); return; }
        setBaseUrl(out.url);
        setStatus("ready");
      } catch (e) {
        setStatus("failed: " + (e && e.message ? e.message : String(e)));
      }
    })();
  }, []);

  const src = baseUrl ? baseUrl + (portrait ? "&orient=portrait" : "") : null;

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        <s-text>
          {status === "ready"
            ? "Production label ready. Use Print to send to your label printer."
            : "Production label status: " + status}
        </s-text>
        <s-checkbox
          checked={portrait}
          onChange={(e) => setPortrait(!!(e && e.target && e.target.checked))}
        >
          Rotate 90 degrees (for printers that feed labels upright)
        </s-checkbox>
      </s-stack>
    </s-admin-print-action>
  );
}
