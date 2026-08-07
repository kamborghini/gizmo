/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

export default async () => {
  render(<Extension />, document.body);
};

function Extension() {
  const { data } = shopify;
  const [src, setSrc] = useState(null);
  const [error, setError] = useState(null);
  const count = (data && data.selected ? data.selected : []).length;

  useEffect(() => {
    const ids = (data && data.selected ? data.selected : []).map((s) => s.id);
    if (!ids.length) return;
    (async () => {
      try {
        // Relative fetch: the extension runtime resolves it against the app's URL
        // and attaches the Authorization header itself (documented behavior). The
        // backend returns a short-lived signed URL the print preview can load
        // without any session.
        const res = await fetch("/print/production-labels/sign", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: ids.join(",") }),
        });
        if (!res.ok) throw new Error("label service responded " + res.status);
        const out = await res.json();
        if (!out.path && !out.url) throw new Error("no document URL returned");
        // Absolute URL: the preview refused a relative path outright (observed:
        // no request issued at all), and the app origin is CORS-open + frameable.
        setSrc(out.url || out.path);
      } catch (e) {
        setError(e && e.message ? e.message : String(e));
      }
    })();
  }, [data && data.selected]);

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        {error ? (
          <s-text>Could not prepare the label ({error}). Please tell support exactly this message.</s-text>
        ) : (
          <s-text>
            {count > 1 ? count + " production labels ready." : "Production label ready."}{" "}
            Use Print to send to your label printer.
          </s-text>
        )}
      </s-stack>
    </s-admin-print-action>
  );
}
