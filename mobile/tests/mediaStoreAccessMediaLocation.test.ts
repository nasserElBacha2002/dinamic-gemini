/**
 * mediaStore hydrate path — ACCESS_MEDIA_LOCATION must not block capture start.
 */
jest.mock('expo-file-system', () => ({
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1024 })),
}));

const getAssetInfoAsync = jest.fn();

jest.mock('expo-media-library', () => ({
  MediaType: { photo: 'photo' },
  SortBy: { creationTime: 'creationTime' },
  getAssetInfoAsync: (...args: unknown[]) => getAssetInfoAsync(...args),
  getAssetsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getPermissionsAsync: jest.fn(),
  addListener: jest.fn(() => ({ remove: jest.fn() })),
}));

import * as MediaLibrary from 'expo-media-library';
import { queryMostRecentPhoto } from '../src/native/mediaStore';

describe('mediaStore ACCESS_MEDIA_LOCATION resilience', () => {
  beforeEach(() => {
    getAssetInfoAsync.mockReset();
    (MediaLibrary.getAssetsAsync as jest.Mock).mockReset();
  });

  it('falls back to asset.uri when getAssetInfoAsync lacks ACCESS_MEDIA_LOCATION', async () => {
    (MediaLibrary.getAssetsAsync as jest.Mock).mockResolvedValue({
      assets: [
        {
          id: '100',
          uri: 'file:///storage/emulated/0/DCIM/IMG_001.jpg',
          filename: 'IMG_001.jpg',
          width: 100,
          height: 80,
          creationTime: 1_700_000_000_000,
          modificationTime: 1_700_000_000_000,
          albumId: '1',
        },
      ],
      hasNextPage: false,
      endCursor: '',
    });
    getAssetInfoAsync.mockRejectedValue(
      new Error('Cannot access ExifInterface because of missing ACCESS_MEDIA_LOCATION permission'),
    );

    const image = await queryMostRecentPhoto();
    expect(image).not.toBeNull();
    expect(image?.uri).toBe('file:///storage/emulated/0/DCIM/IMG_001.jpg');
    expect(image?.displayName).toBe('IMG_001.jpg');
  });

  it('uses localUri from getAssetInfoAsync when available', async () => {
    (MediaLibrary.getAssetsAsync as jest.Mock).mockResolvedValue({
      assets: [
        {
          id: '101',
          uri: 'content://media/external/images/media/101',
          filename: 'IMG_002.jpg',
          width: 10,
          height: 10,
          creationTime: 1_700_000_000_000,
          modificationTime: 1_700_000_000_000,
          albumId: null,
        },
      ],
      hasNextPage: false,
      endCursor: '',
    });
    getAssetInfoAsync.mockResolvedValue({
      localUri: 'file:///data/local/tmp/IMG_002.jpg',
    });

    const image = await queryMostRecentPhoto();
    expect(image?.uri).toBe('file:///data/local/tmp/IMG_002.jpg');
  });
});
