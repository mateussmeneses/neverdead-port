// neverdead - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/rex_app.h>
#include <rex/ui/presenter.h>
#include <rex/ui/window.h>
#include <rex/ui/keybinds.h>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <thread>
#include <atomic>
#include <vector>

class NeverdeadApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<NeverdeadApp>(new NeverdeadApp(ctx, "neverdead",
        PPCImageConfig));
  }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    config.gpu_plugin = "xenos";
  }

  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    (void)drawer;
    rex::ui::RegisterBind("bind_screenshot", "F12", "Capture guest output", [this] {
      CaptureGuestFrame("manual-f12");
    });
  }

  void OnPostSetup() override {
    StartCaptureWorker();
  }

  void OnShutdown() override {
    StopCaptureWorker();
  }

  ~NeverdeadApp() override {
    StopCaptureWorker();
  }

  bool CaptureGuestFrame(const std::string& stage_tag) {
    rex::ui::Presenter* pres = nullptr;
    if (runtime() && runtime()->graphics_system()) {
      pres = runtime()->graphics_system()->presenter();
    }
    if (!pres) return false;

    rex::ui::RawImage img;
    if (!pres->CaptureGuestOutput(img)) {
      return false;
    }

    if (img.width == 0 || img.height == 0 || img.data.empty()) {
      return false;
    }

    std::filesystem::path dir = "analysis/n10-gameplay";
    char env_dir[512] = {0};
    DWORD env_dir_len = GetEnvironmentVariableA("NEVERDEAD_CAPTURE_DIR", env_dir, sizeof(env_dir));
    if (env_dir_len > 0) {
      dir = env_dir;
    }
    std::filesystem::create_directories(dir);

    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    std::tm tm_now{};
    localtime_s(&tm_now, &time_t_now);

    std::ostringstream ss;
    ss << stage_tag << "-" << std::put_time(&tm_now, "%Y%m%d-%H%M%S") << ".bmp";
    std::filesystem::path filepath = dir / ss.str();

    bool ok = SaveRawImageToBmp(filepath, img);
    if (ok) {
      REXLOG_INFO("[D3D12-CAPTURE] Saved {}x{} D3D12 frame to '{}'", img.width, img.height, filepath.string());
    }
    return ok;
  }

 private:
  std::atomic<bool> capture_worker_running_{false};
  std::thread capture_worker_;

  void StartCaptureWorker() {
    if (capture_worker_running_.exchange(true)) return;
    capture_worker_ = std::thread([this]() {
      auto start_time = std::chrono::steady_clock::now();
      int auto_capture_counter = 0;
      char auto_env_buf[32] = {0};
      DWORD env_len = GetEnvironmentVariableA("NEVERDEAD_AUTO_CAPTURE", auto_env_buf, sizeof(auto_env_buf));
      bool auto_mode = (env_len > 0 && auto_env_buf[0] == '1');

      while (capture_worker_running_) {
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        if (!capture_worker_running_) break;

        // Check file trigger in cwd or build dir
        std::filesystem::path trigger_paths[] = {
            "capture_trigger.txt",
            "build/n2-neverdead/capture_trigger.txt"
        };
        for (const auto& tp : trigger_paths) {
          if (std::filesystem::exists(tp)) {
            std::string tag = "trigger";
            try {
              std::ifstream in(tp);
              std::string line;
              if (std::getline(in, line) && !line.empty()) {
                tag = line;
              }
              in.close();
              std::filesystem::remove(tp);
            } catch (...) {
              std::error_code ec;
              std::filesystem::remove(tp, ec);
            }
            CaptureGuestFrame(tag);
          }
        }

        // Auto mode periodic captures
        if (auto_mode) {
          auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
              std::chrono::steady_clock::now() - start_time).count();
          if (elapsed >= 10 && auto_capture_counter == 0) {
            CaptureGuestFrame("01-boot-title");
            auto_capture_counter = 1;
          } else if (elapsed >= 16 && auto_capture_counter == 1) {
            CaptureGuestFrame("02-main-menu");
            auto_capture_counter = 2;
          } else if (elapsed >= 22 && auto_capture_counter == 2) {
            CaptureGuestFrame("04-prologue-cutscene");
            auto_capture_counter = 3;
          } else if (elapsed >= 30 && auto_capture_counter == 3) {
            CaptureGuestFrame("05-gameplay-entry");
            auto_capture_counter = 4;
          } else if (elapsed >= 36 && auto_capture_counter == 4) {
            CaptureGuestFrame("06-character-movement");
            auto_capture_counter = 5;
          }
        }
      }
    });
  }

  void StopCaptureWorker() {
    if (capture_worker_running_.exchange(false)) {
      if (capture_worker_.joinable()) {
        capture_worker_.join();
      }
    }
  }

  static bool SaveRawImageToBmp(const std::filesystem::path& path, const rex::ui::RawImage& img) {
    if (img.width == 0 || img.height == 0 || img.data.empty()) return false;
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    if (!out) return false;

    uint32_t row_stride = (img.width * 3 + 3) & ~3;
    uint32_t data_size = row_stride * img.height;
    uint32_t file_size = 54 + data_size;

    uint8_t header[54] = {
        'B', 'M',
        uint8_t(file_size), uint8_t(file_size >> 8), uint8_t(file_size >> 16), uint8_t(file_size >> 24),
        0, 0, 0, 0,
        54, 0, 0, 0,
        40, 0, 0, 0,
        uint8_t(img.width), uint8_t(img.width >> 8), uint8_t(img.width >> 16), uint8_t(img.width >> 24),
        uint8_t(img.height), uint8_t(img.height >> 8), uint8_t(img.height >> 16), uint8_t(img.height >> 24),
        1, 0, // planes
        24, 0, // 24-bpp RGB
        0, 0, 0, 0, // uncompressed BI_RGB
        uint8_t(data_size), uint8_t(data_size >> 8), uint8_t(data_size >> 16), uint8_t(data_size >> 24),
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0
    };
    out.write(reinterpret_cast<const char*>(header), 54);

    std::vector<uint8_t> row_buf(row_stride, 0);
    const uint8_t* src = img.data.data();

    for (int y = int(img.height) - 1; y >= 0; --y) {
      const uint8_t* src_row = src + y * img.stride;
      for (uint32_t x = 0; x < img.width; ++x) {
        // RawImage has RGBA bytes in 8bpc
        uint8_t r = src_row[x * 4 + 0];
        uint8_t g = src_row[x * 4 + 1];
        uint8_t b = src_row[x * 4 + 2];
        row_buf[x * 3 + 0] = b;
        row_buf[x * 3 + 1] = g;
        row_buf[x * 3 + 2] = r;
      }
      out.write(reinterpret_cast<const char*>(row_buf.data()), row_stride);
    }
    return true;
  }
};
