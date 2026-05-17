/**
 * T-V3-C-19 / (email) route group layout.
 *
 * The email-template preview screens (S-056〜S-060) are operator-facing
 * previews of the templated emails dispatched by `backend/routers/email.py`
 * (F-028 / T-V3-B-30). They render without the workspace sidebar so the
 * preview occupies the full viewport and resembles the customer inbox view.
 * T-V3-C-17 / (email) route group layout.
 *
 * The email-template preview screens (S-056 〜 S-060) render the actual outbound
 * email body inside a "mail-client" frame and intentionally bypass the
 * workspace Sidebar that the root layout wraps every page in. This route-group
 * layout therefore renders {children} alone so the preview pages can occupy
 * the full viewport (matching the mock).
 * T-V3-C-18..C-21 / (email) route group layout.
 *
 * Email-template preview screens (S-056..S-060) deliberately bypass the
 * authenticated workspace chrome — they render *inside* the recipient's
 * mailbox at runtime, so the in-app Sidebar / TopBar are not appropriate.
 * Rendering just {children} keeps the preview iframe pixel-parity with what
 * the email client will display.
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
