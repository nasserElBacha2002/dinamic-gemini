/** Generic list row for image/video asset drawers (inventory references, aisle uploads, etc.). */
export interface ManagedImageAssetItem {
  id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  created_at: string;
}
