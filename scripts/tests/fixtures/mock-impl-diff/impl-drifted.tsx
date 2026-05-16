/**
 * Drifted fixture screen for T-FOUNDATION-02 lint-mock-impl-diff self-test.
 *
 * The values below intentionally diverge from the corresponding mock to
 * exercise drift detection. The screen-id is still S-902 so the impl
 * resolves, but feature-id / task-ids / entities / phase differ.
 *
 * @screen-id S-902
 * @feature-id F-999
 * @task-ids T-902-01
 * @entities users
 * @phase P2
 */
import * as React from "react";

export default function S902DriftedScreen(): React.ReactElement {
  return (
    <div
      data-screen-id="S-902"
      data-feature-id="F-999"
      data-task-ids="T-902-01"
      data-entities="users"
      data-phase="P2"
    >
      <h1>Drifted fixture screen</h1>
    </div>
  );
}
