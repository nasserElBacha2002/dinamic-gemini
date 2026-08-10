/**
 * Physical product label mint API (D1).
 */

import { V3_CLIENTS_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';

export interface IssuedProductLabel {
  label_id: string;
  internal_code: string;
  quantity: number;
  format_version: string;
  checksum: string;
  payload: string;
  created_at: string;
}

export interface IssueProductLabelsRequest {
  internal_code: string;
  quantity: number;
  count?: number;
}

export interface IssueProductLabelsResponse {
  items: IssuedProductLabel[];
}

export async function issueProductLabels(
  clientId: string,
  body: IssueProductLabelsRequest
): Promise<IssueProductLabelsResponse> {
  return apiRequestJson<IssueProductLabelsResponse>(
    `${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/product-labels`,
    {
      method: 'POST',
      body: JSON.stringify({
        internal_code: body.internal_code,
        quantity: body.quantity,
        count: body.count ?? 1,
      }),
    }
  );
}
