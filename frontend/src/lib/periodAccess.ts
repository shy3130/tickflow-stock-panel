import type { CapabilitiesResponse } from './api'

export function hasMonthlyAccess(caps?: CapabilitiesResponse | null): boolean {
  return !!caps?.monthly_access
}

export function hasYearlyAccess(caps?: CapabilitiesResponse | null): boolean {
  return !!caps?.yearly_access
}
