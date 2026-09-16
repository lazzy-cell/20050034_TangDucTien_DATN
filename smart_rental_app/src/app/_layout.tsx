import { Stack, router, usePathname } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { addNotificationListeners, registerAndroidPushToken } from "../lib/notifications";
import { onAuthStateChanged, restoreSession } from "../lib/firebase";

export default function RootLayout() {
  const pathname = usePathname();
  const [authReady, setAuthReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let mounted = true;

    const unsubscribe = onAuthStateChanged((isAuthenticated) => {
      if (!mounted) return;

      setAuthenticated(isAuthenticated);
      setAuthReady(true);

      if (isAuthenticated && pathname === "/") {
        router.replace("/home");
      } else if (!isAuthenticated && pathname !== "/") {
        router.replace("/");
      }
    });

    restoreSession()
      .then((session) => {
        if (!mounted) return;

        const isTenant = session?.profile?.role === "tenant";
        setAuthenticated(isTenant);
        setAuthReady(true);

        if (isTenant && pathname === "/") {
          router.replace("/home");
        } else if (!isTenant && pathname !== "/") {
          router.replace("/");
        }
      })
      .catch(() => {
        if (!mounted) return;
        setAuthenticated(false);
        setAuthReady(true);
        if (pathname !== "/") router.replace("/");
      });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!authReady) return;

    if (authenticated && pathname === "/") {
      router.replace("/home");
    } else if (!authenticated && pathname !== "/") {
      router.replace("/");
    }
  }, [authReady, authenticated, pathname]);

  useEffect(() => {
    if (!authReady || !authenticated) return;
    // Re-register on every authenticated app start so token rotations and
    // reinstalls cannot leave targeted notifications pointing at stale data.
    registerAndroidPushToken().catch((error) => {
      console.warn("[notifications] token refresh failed", error);
    });
  }, [authReady, authenticated]);

  useEffect(() => {
    return addNotificationListeners(
      (notification) => {
        console.log(
          "[notifications] received",
          notification.request.content.data,
        );
      },
      (response) => {
        const data = response.notification.request.content.data as Record<
          string,
          unknown
        >;
        const type = String(data?.type || "");

        if (type === "bill") {
          router.push("/bill");
        } else {
          router.push("/notifications");
        }
      },
    );
  }, []);

  return (
    <>
      <Stack
        screenOptions={{
          headerShown: false,
        }}
      />
      {!authReady && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#2563EB" />
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#F5F7FB",
    alignItems: "center",
    justifyContent: "center",
  },
});
