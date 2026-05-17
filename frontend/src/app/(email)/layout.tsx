/**
 * T-V3-C-17 / (email) route group layout.
 *
 * The email-template preview screens (S-056 〜 S-060) render the actual outbound
 * email body inside a "mail-client" frame and intentionally bypass the
 * workspace Sidebar that the root layout wraps every page in. This route-group
 * layout therefore renders {children} alone so the preview pages can occupy
 * the full viewport (matching the mock).
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
