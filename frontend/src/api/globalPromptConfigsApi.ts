import {
  globalPromptConfigActivatePath,
  globalPromptConfigByIdPath,
  globalPromptConfigsActivePath,
  globalPromptConfigsPath,
} from '../constants/v3ApiPaths';
import type {
  CreateGlobalPromptConfigRequest,
  GlobalPromptConfig,
  GlobalPromptConfigsListResponse,
} from './types';
import { handleResponse, protectedFetch } from './http';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export async function listGlobalPromptConfigs(): Promise<GlobalPromptConfigsListResponse> {
  const response = await protectedFetch(`${API_BASE}${globalPromptConfigsPath()}`);
  return handleResponse<GlobalPromptConfigsListResponse>(response);
}

export async function createGlobalPromptConfigVersion(
  body: CreateGlobalPromptConfigRequest
): Promise<GlobalPromptConfig> {
  const response = await protectedFetch(`${API_BASE}${globalPromptConfigsPath()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<GlobalPromptConfig>(response);
}

export async function getActiveGlobalPromptConfig(): Promise<GlobalPromptConfig> {
  const response = await protectedFetch(`${API_BASE}${globalPromptConfigsActivePath()}`);
  return handleResponse<GlobalPromptConfig>(response);
}

export async function getGlobalPromptConfigById(configId: string): Promise<GlobalPromptConfig> {
  const response = await protectedFetch(`${API_BASE}${globalPromptConfigByIdPath(configId)}`);
  return handleResponse<GlobalPromptConfig>(response);
}

export async function activateGlobalPromptConfigVersion(
  configId: string
): Promise<GlobalPromptConfig> {
  const response = await protectedFetch(`${API_BASE}${globalPromptConfigActivatePath(configId)}`, {
    method: 'POST',
  });
  return handleResponse<GlobalPromptConfig>(response);
}
