export type TenantProfile = {
  id?: string;
  uid?: string;
  email?: string;
  name?: string;
  phone?: string;
  address?: string;
  status?: string;
  role?: string;
  [key: string]: unknown;
};

export type TenantRoom = {
  id: string;
  room_id?: string;
  room_name?: string;
  status?: string;
  occupied?: boolean;
  tenant_id?: string | null;
  [key: string]: unknown;
};

let selectedRoom: TenantRoom | null = null;
let profile: TenantProfile | null = null;

export function setSelectedRoom(room: TenantRoom | null) { selectedRoom = room; }
export function getSelectedRoom() { return selectedRoom; }
export function setProfile(value: TenantProfile | null) { profile = value; }
export function getProfile() { return profile; }
export function clearSession() { selectedRoom = null; profile = null; }
