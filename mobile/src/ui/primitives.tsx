import { FlatList, Image, Text, TextInput, TouchableOpacity, View } from 'react-native';

import type { CapturePhotoRow } from '../database/schema/captureSchema';
import { styles } from './styles';

export function Shell({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <View style={styles.container}>
      <Text style={styles.h1}>{title}</Text>
      <View style={styles.body}>{children}</View>
      {footer}
    </View>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Input(props: React.ComponentProps<typeof TextInput>) {
  return <TextInput placeholderTextColor="#94a3b8" style={styles.input} {...props} />;
}

export function Button({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <TouchableOpacity style={[styles.btn, disabled && styles.btnDisabled]} disabled={disabled} onPress={onPress}>
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

export function SmallButton({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[styles.smallBtn, disabled && styles.btnDisabled]}
      disabled={disabled}
      onPress={onPress}
    >
      <Text style={styles.smallBtnText}>{label}</Text>
    </TouchableOpacity>
  );
}

export function ErrorText({ text }: { text: string }) {
  return <Text style={styles.error}>{text}</Text>;
}

export function PhotoWorkList({
  photos,
  onExclude,
  onReinclude,
  header,
}: {
  photos: CapturePhotoRow[];
  onExclude: (assetId: string) => void;
  onReinclude: (assetId: string) => void;
  header: React.ReactElement;
}) {
  return (
    <FlatList
      data={photos}
      keyExtractor={(item) => item.asset_id}
      numColumns={2}
      columnWrapperStyle={styles.gridRow}
      initialNumToRender={10}
      maxToRenderPerBatch={10}
      windowSize={7}
      removeClippedSubviews
      ListHeaderComponent={header}
      ListEmptyComponent={<Text style={styles.muted}>Sin fotografías.</Text>}
      renderItem={({ item: photo }) => (
        <View style={styles.photoCard}>
          <Image source={{ uri: photo.uri }} style={styles.thumb} />
          <Text style={styles.photoText} numberOfLines={1}>
            {photo.display_name}
          </Text>
          <Text style={styles.photoText}>
            [{photo.status}] {photo.width}x{photo.height}
          </Text>
          {photo.status === 'excluded' ? (
            <SmallButton label="Reincorporar" onPress={() => onReinclude(photo.asset_id)} />
          ) : (
            <SmallButton label="Excluir" onPress={() => onExclude(photo.asset_id)} />
          )}
        </View>
      )}
    />
  );
}
