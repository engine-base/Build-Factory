/**
 * T-V3-C-41 / (onboarding) route group layout.
 *
 * The onboarding screens (S-048 welcome / S-049 workspace-setup / S-050
 * AI 社員紹介) intentionally bypass the workspace Sidebar that the root layout
 * wraps every page in. This route-group layout therefore renders {children}
 * alone so the full-bleed S-050 mock layout can occupy the viewport.
 *
 * @screen-id S-048,S-049,S-050
 */
export default function OnboardingGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
