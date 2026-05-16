/**
 * Aligned fixture screen for T-FOUNDATION-02 lint-mock-impl-diff self-test.
 *
 * @screen-id S-901
 * @feature-id F-901
 * @task-ids T-901-01,T-901-02
 * @entities users,sessions
 * @phase P1
 */
import * as React from "react";

export default function S901AlignedScreen(): React.ReactElement {
  return (
    <div
      data-screen-id="S-901"
      data-feature-id="F-901"
      data-task-ids="T-901-01,T-901-02"
      data-entities="users,sessions"
      data-phase="P1"
    >
      <h1>Aligned fixture screen</h1>
    </div>
  );
}
