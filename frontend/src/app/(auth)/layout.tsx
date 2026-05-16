/**
 * T-V3-C-05 / (auth) route group layout.
 *
 * The unauthenticated screens (login / signup / 2fa / forgot / oauth-callback)
 * intentionally bypass the workspace Sidebar that the root layout wraps every
 * page in. This route-group layout therefore renders {children} alone so the
 * S-005 page can occupy the full viewport (matching the mock).
 *
 * @screen-id S-001,S-002,S-003,S-004,S-005
 */
export default function AuthGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
