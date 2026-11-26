import { notify } from '../../apps/desktop/src/store/notifications.ts'

export { Badge } from '../../apps/desktop/src/components/ui/badge.tsx'
export { Button } from '../../apps/desktop/src/components/ui/button.tsx'
export { Codicon } from '../../apps/desktop/src/components/ui/codicon.tsx'
export {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '../../apps/desktop/src/components/ui/dialog.tsx'
export { Input } from '../../apps/desktop/src/components/ui/input.tsx'
export { Textarea } from '../../apps/desktop/src/components/ui/textarea.tsx'

export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const PALETTE_AREA = 'palette'
export const host = { state: { gateway: 'open' }, notify }
export const useValue = state => state
