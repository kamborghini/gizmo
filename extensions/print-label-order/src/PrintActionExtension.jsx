/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

const SIZES = [
  { value: "4x2", label: "4 x 2 in (102 x 51 mm)" },
  { value: "4x3", label: "4 x 3 in (102 x 76 mm)" },
  { value: "4x6", label: "4 x 6 in (102 x 152 mm)" },
  { value: "2x4", label: "2 x 4 in (51 x 102 mm)" },
  { value: "a4", label: "A4 page" },
];

export default async () => {
  render(<Extension />, document.body);
};

function Extension() {
  const { data } = shopify;
  const [baseUrl, setBaseUrl] = useState(null);
  const [size, setSize] = useState("4x2");
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

  const src = baseUrl
    ? baseUrl + "&size=" + size + (portrait ? "&orient=portrait" : "")
    : null;

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        <s-text>
          {status === "ready"
            ? "Production label ready. Choose the label size, then Print."
            : "Production label status: " + status}
        </s-text>
        <s-select
          label="Label size"
          value={size}
          onChange={(e) => e && e.target && e.target.value && setSize(e.target.value)}
        >
          {SIZES.map((o) => (
            <s-option value={o.value} defaultSelected={o.value === "4x2" ? true : undefined}>
              {o.label}
            </s-option>
          ))}
        </s-select>
        <s-checkbox
          label="Rotate 90 degrees (for printers that feed labels upright)"
          checked={portrait}
          onChange={(e) => setPortrait(!!(e && e.target && e.target.checked))}
        ></s-checkbox>
      </s-stack>
    </s-admin-print-action>
  );
}
