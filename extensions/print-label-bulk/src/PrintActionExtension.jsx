/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

const SIZES = [
  { value: "4x2", label: "4 x 2 in (102 x 51 mm)" },
  { value: "4x3", label: "4 x 3 in (102 x 76 mm)" },
  { value: "4x4", label: "4 x 4 in (102 x 102 mm)" },
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
  const [size, setSize] = useState("4x6");
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
        // Open on the production printer's saved stock: which roll is loaded
        // is a shop setting, not something chosen here. Still changeable below.
        if (out.size && SIZES.some((o) => o.value === out.size)) setSize(out.size);
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
        {/* Printing here renders the labels and changes nothing else: this
            frame carries no gizmo session, so the document is read-only by
            design. Saying so beats letting the order sit in Unprocessed. */}
        {status === "ready" ? (
          <s-text color="subdued">
            These orders still need Ready to make in Reactor to move into production
            and, on an account order, to start the 30-day payment terms.
          </s-text>
        ) : null}
        {/* Held until the label is ready: the saved size lands then, and a
            size picked before it would be overwritten. */}
        <s-select
          label="Label size"
          value={size}
          disabled={status !== "ready"}
          onChange={(e) => {
            // Typed as a plain Event; what changed is the select itself.
            const sel = /** @type {{ value?: string } | null} */ (/** @type {unknown} */ (e && e.target));
            if (sel && sel.value) setSize(sel.value);
          }}
        >
          {SIZES.map((o) => (
            <s-option value={o.value} defaultSelected={o.value === size ? true : undefined}>
              {o.label}
            </s-option>
          ))}
        </s-select>
        <s-checkbox
          label="Rotate 90 degrees (for printers that feed labels upright)"
          checked={portrait}
          onChange={(e) => {
            const box = /** @type {{ checked?: boolean } | null} */ (/** @type {unknown} */ (e && e.target));
            setPortrait(!!(box && box.checked));
          }}
        ></s-checkbox>
      </s-stack>
    </s-admin-print-action>
  );
}
