/**
 * T-V3-C-19 / (email) route group layout.
 *
 * The email-template preview screens (S-056〜S-060) are operator-facing
 * previews of the templated emails dispatched by `backend/routers/email.py`
 * (F-028 / T-V3-B-30). They render without the workspace sidebar so the
 * preview occupies the full viewport and resembles the customer inbox view.
 *
 * @screen-id S-056,S-057,S-058,S-059,S-060
 */
export default function EmailGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
