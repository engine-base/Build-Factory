/**
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
