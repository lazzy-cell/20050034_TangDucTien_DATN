import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import { Platform } from "react-native";
import { apiPost } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

let registeredToken: string | null = null;

export async function setupAndroidNotifications() {
  if (Platform.OS !== "android" || !Device.isDevice) {
    return { token: null, reason: "android-device-required" as const };
  }

  const permissions = await Notifications.getPermissionsAsync();
  let status = permissions.status;
  if (status !== "granted") {
    status = (await Notifications.requestPermissionsAsync()).status;
  }
  if (status !== "granted") {
    return { token: null, reason: "permission-denied" as const };
  }

  const channels = [
    {
      id: "default",
      name: "Thông báo chung",
      description: "Thông báo Smart Rental",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
    },
    {
      id: "alerts",
      name: "Cảnh báo & sự cố",
      description: "Cảnh báo điện, occupancy và sự cố hệ thống",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 300, 200, 300],
    },
    {
      id: "power",
      name: "Điện phòng",
      description: "Thông báo bật/ngắt điện",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 200, 150, 200],
    },
    {
      id: "bills",
      name: "Hóa đơn",
      description: "Hóa đơn, thanh toán và công nợ",
      importance: Notifications.AndroidImportance.DEFAULT,
    },
    {
      id: "admin",
      name: "Tin nhắn từ quản trị",
      description: "Thông báo trực tiếp từ quản trị viên",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 200, 250],
    },
  ];

  for (const channel of channels) {
    await Notifications.setNotificationChannelAsync(channel.id, {
      name: channel.name,
      description: channel.description,
      importance: channel.importance,
      vibrationPattern: channel.vibrationPattern,
      sound: "default",
      enableVibrate: true,
      enableLights: true,
    });
  }

  const native = await Notifications.getDevicePushTokenAsync();
  return { token: String(native.data), reason: "ok" as const };
}

export async function registerAndroidPushToken() {
  const result = await setupAndroidNotifications();
  if (!result.token) return result;

  await apiPost("/api/notifications/register", {
    token: result.token,
    token_type: "fcm",
    platform: "android",
    device_name: Device.deviceName || Device.modelName || "Android",
  });
  registeredToken = result.token;
  return result;
}

export async function unregisterAndroidPushToken() {
  if (!registeredToken) return;
  try {
    await apiPost("/api/notifications/unregister", { token: registeredToken });
  } finally {
    registeredToken = null;
  }
}

export function addNotificationListeners(
  onNotification?: (notification: Notifications.Notification) => void,
  onResponse?: (response: Notifications.NotificationResponse) => void,
) {
  const received = onNotification
    ? Notifications.addNotificationReceivedListener(onNotification)
    : null;
  const response = onResponse
    ? Notifications.addNotificationResponseReceivedListener(onResponse)
    : null;

  return () => {
    received?.remove();
    response?.remove();
  };
}

export { Notifications };
