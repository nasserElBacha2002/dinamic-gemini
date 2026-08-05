import {
  FlatList,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import type { CapturePhotoRow } from '../database/schema/captureSchema';
import { styles } from './styles';

/** Bottom inset for FlatList content when Shell did not already reserve footer space. */
export function useShellBottomInset(footerHeight = 0): number {
  const insets = useSafeAreaInsets();
  return footerHeight + insets.bottom + 12;
}

export function Shell({
  title,
  children,
  footer,
  scroll = false,
  keyboardAware = false,
  contentPaddingBottom = 0,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Wrap body in ScrollView (do not use with FlatList screens). */
  scroll?: boolean;
  /** KeyboardAvoidingView around scrollable body (Login / forms). */
  keyboardAware?: boolean;
  /** Measured app footer height — reserved so content is not covered. */
  contentPaddingBottom?: number;
}) {
  const insets = useSafeAreaInsets();
  const bottomPad = contentPaddingBottom + (footer ? 0 : insets.bottom);

  const body = scroll ? (
    <ScrollView
      style={styles.body}
      contentContainerStyle={{ paddingBottom: bottomPad + 16, flexGrow: 1 }}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.body, { paddingBottom: bottomPad }]}>{children}</View>
  );

  const maybeKeyboard = keyboardAware ? (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
    >
      {body}
    </KeyboardAvoidingView>
  ) : (
    body
  );

  return (
    <SafeAreaView style={styles.container} edges={['top', 'left', 'right']}>
      <Text style={styles.h1}>{title}</Text>
      {maybeKeyboard}
      {footer ? (
        <View style={{ paddingBottom: Math.max(insets.bottom, 8) }}>{footer}</View>
      ) : null}
    </SafeAreaView>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

export function Input(props: React.ComponentProps<typeof TextInput>) {
  return <TextInput placeholderTextColor="#94a3b8" style={styles.input} {...props} />;
}

export function PasswordInput({
  value,
  onChangeText,
  placeholder = 'Contraseña',
  visible,
  onToggleVisible,
  editable = true,
  ...rest
}: {
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
  visible: boolean;
  onToggleVisible: () => void;
  editable?: boolean;
} & Omit<
  React.ComponentProps<typeof TextInput>,
  'value' | 'onChangeText' | 'secureTextEntry' | 'placeholder'
>) {
  return (
    <View style={styles.passwordRow}>
      <TextInput
        {...rest}
        placeholder={placeholder}
        placeholderTextColor="#94a3b8"
        style={[styles.input, styles.passwordInput]}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={!visible}
        autoCapitalize="none"
        autoCorrect={false}
        textContentType="password"
        editable={editable}
      />
      <TouchableOpacity
        style={styles.passwordToggle}
        onPress={onToggleVisible}
        accessibilityRole="button"
        accessibilityLabel={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
        accessibilityState={{ selected: visible }}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Text style={styles.passwordToggleText}>{visible ? 'Ocultar' : 'Mostrar'}</Text>
      </TouchableOpacity>
    </View>
  );
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
  readOnly = false,
}: {
  photos: CapturePhotoRow[];
  onExclude: (assetId: string) => void;
  onReinclude: (assetId: string) => void;
  header: React.ReactElement;
  readOnly?: boolean;
}) {
  // Shell already reserves footer height on the body; keep light bottom padding for last row.
  return (
    <FlatList
      data={photos}
      keyExtractor={(item) => item.asset_id}
      numColumns={2}
      columnWrapperStyle={styles.gridRow}
      contentContainerStyle={{ paddingBottom: 24 } as StyleProp<ViewStyle>}
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
          {readOnly ? null : photo.status === 'excluded' ? (
            <SmallButton label="Reincorporar" onPress={() => onReinclude(photo.asset_id)} />
          ) : (
            <SmallButton label="Excluir" onPress={() => onExclude(photo.asset_id)} />
          )}
        </View>
      )}
    />
  );
}
