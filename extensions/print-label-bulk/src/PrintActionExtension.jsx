/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

export default async () => {
  render(<Extension />, document.body);
};

function Extension() {
  const { data } = shopify;
  const [src, setSrc] = useState(null);
  // The panel is the only visible surface inside this sandbox, so it reports the
  // exact state instead of a static message that can mask a silent failure.
  const [status, setStatus] = useState("starting");

  useEffect(() => {
    const sel = (data && data.selected) || [];
    const ids = sel.map((s) => s && s.id).filter(Boolean);
    if (!ids.length) {
      setStatus("no order was passed to this action (selected=" + JSON.stringify(sel).slice(0, 120) + ")");
      return;
    }
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
        setSrc(out.url);
        setStatus("document ready: " + out.url.slice(0, 90));
      } catch (e) {
        setStatus("fetch failed: " + (e && e.message ? e.message : String(e)));
      }
    })();
  }, []);

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        <s-text>Production label status: {status}</s-text>
      </s-stack>
    </s-admin-print-action>
  );
}
