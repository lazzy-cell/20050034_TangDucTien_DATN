(function () {

  const form = document.getElementById("loginForm");
  const errorBox = document.getElementById("errorBox");
  const btn = document.getElementById("loginBtn");

  firebaseAuth.onAuthStateChanged(async (user) => {

    if (!user) {
      return;
    }

    try {

      const tokenResult =
        await user.getIdTokenResult();

      const role =
        tokenResult.claims.role;

      if (role === "landlord") {
        window.location.href = "/dashboard";
        return;
      }

      if (role === "tenant") {
        window.location.href = "/tenant";
        return;
      }

      await firebaseAuth.signOut();

      errorBox.textContent =
        "Tài khoản không có vai trò hợp lệ.";

      errorBox.classList.remove("hidden");

    } catch (error) {

      console.error(error);

    }
  });


  form.addEventListener("submit", async (e) => {

    e.preventDefault();

    errorBox.classList.add("hidden");

    btn.disabled = true;
    btn.textContent = "Đang đăng nhập…";

    const email =
      document.getElementById("email").value.trim();

    const password =
      document.getElementById("password").value;

    try {

      const credential =
        await firebaseAuth.signInWithEmailAndPassword(
          email,
          password
        );

      const user = credential.user;

      // Force refresh để chắc chắn lấy role mới nhất
      const tokenResult =
        await user.getIdTokenResult(true);

      const role =
        tokenResult.claims.role;

      if (role === "landlord") {
        window.location.href = "/dashboard";
        return;
      }

      if (role === "tenant") {
        window.location.href = "/tenant";
        return;
      }

      await firebaseAuth.signOut();
      throw new Error("Tài khoản không có vai trò hợp lệ.");

    } catch (err) {

      console.error(err);

      let message =
        "Đăng nhập thất bại.";

      if (
        err.code ===
        "auth/invalid-credential"
      ) {
        message =
          "Email hoặc mật khẩu không đúng.";
      }

      if (
        err.code ===
        "auth/user-disabled"
      ) {
        message =
          "Tài khoản đã bị vô hiệu hóa.";
      }

      if (
        err.message ===
        "Tài khoản không có vai trò hợp lệ."
      ) {
        message = err.message;
      }

      errorBox.textContent = message;
      errorBox.classList.remove("hidden");

    } finally {

      btn.disabled = false;
      btn.textContent = "Đăng nhập";

    }
  });

})();