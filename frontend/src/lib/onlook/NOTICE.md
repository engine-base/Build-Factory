# Onlook Notice

Build-Factory uses code derived from Onlook (https://github.com/onlook-dev/onlook), licensed under Apache License 2.0.

Copyright 2024 On Off, Inc.

The following directories contain code derived from Onlook:
- frontend/src/lib/onlook/  (extracted from packages/{penpal,constants,models,utility,parser})
- frontend/src/components/design-canvas/  (extracted from apps/web/client/src/app/project/[id]/_components/canvas and components/store/editor)

Modifications: dependencies on @onlook/db, @onlook/code-provider, @onlook/git, @onlook/github, @onlook/stripe, @supabase/ssr, @trpc/*, @xterm/*, @zenfs/* removed; import paths rewritten for Build-Factory.

See https://www.apache.org/licenses/LICENSE-2.0 for license terms.
