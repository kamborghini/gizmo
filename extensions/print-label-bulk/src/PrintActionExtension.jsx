/** @jsxImportSource preact */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

const APP_URL = "https://gizmo-production-c8c1.up.railway.app";

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
        // The admin's preview frame carries no session, so trade the merchant's id
        // token for a short-lived signed document URL the preview can load freely.
        const token = await shopify.auth.idToken();
        const res = await fetch(APP_URL + "/print/production-labels/sign", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
          body: JSON.stringify({ ids: ids.join(",") }),
        });
        if (!res.ok) throw new Error("label service responded " + res.status);
        const out = await res.json();
        if (!out.url) throw new Error("no document URL returned");
        setSrc(out.url);
      } catch (e) {
        setError(e && e.message ? e.message : String(e));
      }
    })();
  }, [data && data.selected]);

  return (
    <s-admin-print-action src={src}>
      <s-stack direction="block" gap="base">
        {error ? (
          <s-text>Could not prepare the label ({error}). Close this, refresh the page and try again.</s-text>
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
