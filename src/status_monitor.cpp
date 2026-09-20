#include <array>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "zsibot_sdk/zsibot_api.h"

namespace {

std::atomic<bool> g_exit_now{false};

void handleSignal(int)
{
    g_exit_now.store(true);
}

struct Options
{
    std::string host = "192.168.234.1";
    uint32_t send_port = 8081;
    uint32_t recv_port = 8080;
    double duration_seconds = 10.0;
    double rate_hz = 2.0;
};

void usage(const char* program)
{
    std::cerr
        << "Usage: " << program << " [options]\n"
        << "  --host ADDRESS      robot address (default 192.168.234.1)\n"
        << "  --send-port PORT    SDK command port (default 8081)\n"
        << "  --recv-port PORT    local SDK receive port (default 8080)\n"
        << "  --duration SECONDS  required timeout in seconds (default 10)\n"
        << "  --rate HZ           display rate, 0.1 to 10 (default 2)\n"
        << "  --help              show this help\n";
}

Options parseOptions(int argc, char** argv, bool& ok)
{
    Options options;
    ok = true;

    for (int i = 1; i < argc; ++i) {
        const std::string argument = argv[i];

        auto requireValue = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                std::cerr << "Missing value for " << name << "\n";
                ok = false;
                return {};
            }
            return argv[++i];
        };

        try {
            if (argument == "--help") {
                usage(argv[0]);
                ok = false;
                return options;
            } else if (argument == "--host") {
                options.host = requireValue("--host");
            } else if (argument == "--send-port") {
                options.send_port = std::stoul(requireValue("--send-port"));
            } else if (argument == "--recv-port") {
                options.recv_port = std::stoul(requireValue("--recv-port"));
            } else if (argument == "--duration") {
                options.duration_seconds = std::stod(requireValue("--duration"));
            } else if (argument == "--rate") {
                options.rate_hz = std::stod(requireValue("--rate"));
            } else {
                std::cerr << "Unknown option: " << argument << "\n";
                usage(argv[0]);
                ok = false;
                return options;
            }
        } catch (const std::exception&) {
            std::cerr << "Invalid value for " << argument << "\n";
            ok = false;
            return options;
        }
    }

    if (options.host.empty() || options.send_port == 0 || options.recv_port == 0 ||
        options.send_port > 65535 || options.recv_port > 65535 ||
        options.duration_seconds < 0.0 || options.rate_hz < 0.1 ||
        options.rate_hz > 10.0) {
        std::cerr << "One or more options are outside their valid range\n";
        usage(argv[0]);
        ok = false;
    }

    return options;
}

template <typename T>
std::string enumValue(T value)
{
    return std::to_string(static_cast<int>(value));
}

std::string boolValue(bool value)
{
    return value ? "true" : "false";
}

constexpr float kRadiansToDegrees = 180.0f / 3.14159265358979323846f;

void printVector(const std::string& label, const std::array<float, 3>& values,
                 const std::string& unit)
{
    std::cout << label << "=" << values[0] << "," << values[1] << "," << values[2]
              << unit << "\n";
}

void printState(const zsibot::ZsibotExecutor& executor)
{
    const bool connected = executor.IsConnected();
    const zsibot::BatteryInfo battery = executor.GetBatteryInfo();
    const std::array<float, 4> quaternion = executor.GetQuaternion();
    const std::array<float, 3> rpy_rad = executor.GetRPY();
    const std::array<float, 3> position = executor.GetPosition();
    const std::array<float, 3> body_velocity = executor.GetBodyVelocity();
    const std::array<float, 3> body_gyro = executor.GetBodyGyro();
    const std::array<float, 3> body_acceleration = executor.GetBodyAcc();
    const zsibot::SpeedInfo speed = executor.GetSpeed();
    const std::vector<zsibot::FaultInfo> faults = executor.GetFaultInfo();

    std::cout << "\n--- L1-W state ---\n"
              << "connected=" << boolValue(connected) << "\n"
              << "battery power=" << executor.GetPower()
              << "% voltage=" << battery.volt
              << "V current=" << battery.current
              << "A temp=" << battery.temp
              << "C error=" << battery.error << "\n"
              << "quaternion wxyz=" << quaternion[0] << "," << quaternion[1] << ","
              << quaternion[2] << "," << quaternion[3] << "\n"
              << "rpy rad=" << rpy_rad[0] << "," << rpy_rad[1] << "," << rpy_rad[2]
              << " deg=" << rpy_rad[0] * kRadiansToDegrees << ","
              << rpy_rad[1] * kRadiansToDegrees << ","
              << rpy_rad[2] * kRadiansToDegrees << "\n";

    printVector("position xyz", position, "m");
    printVector("body velocity xyz", body_velocity, "m/s");
    printVector("body gyro xyz", body_gyro, "rad/s");
    printVector("body acceleration xyz", body_acceleration, "m/s^2");

    std::cout << "measured forward=" << speed.speed
              << "m/s lateral=" << speed.shift_speed
              << "m/s yaw_rate=" << speed.angle_speed
              << "rad/s yaw_angle=" << speed.angle << "rad\n"
              << "speed_level=" << enumValue(executor.GetSpeedLevel())
              << " function_mode=" << enumValue(executor.GetFunctionMode())
              << " control_mode=" << enumValue(executor.GetControlMode())
              << " motion_mode=" << enumValue(executor.GetMotionMode())
              << " motion_type=" << enumValue(executor.GetMotionType()) << "\n";

    std::cout << "fault_count=" << faults.size() << "\n";
    for (const zsibot::FaultInfo& fault : faults) {
        std::cout << "  fault module=" << fault.module
                  << " submodule=" << fault.submodule
                  << " code=" << fault.error_code
                  << " level=" << fault.level
                  << " info=" << fault.info << "\n";
    }
}

}  // namespace

int main(int argc, char** argv)
{
    for (int i = 1; i < argc; ++i) {
        if (std::string(argv[i]) == "--help") {
            usage(argv[0]);
            return 0;
        }
    }

    bool options_valid = false;
    const Options options = parseOptions(argc, argv, options_valid);
    if (!options_valid) {
        return 2;
    }

    std::signal(SIGINT, handleSignal);
    std::signal(SIGTERM, handleSignal);

    if (options.duration_seconds <= 0.0) {
        std::cerr << "Use a finite --duration for this first status test. Ctrl+C "
                     "does not interrupt SDK construction when no robot replies.\n";
        return 2;
    }

    try {
        const auto period = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::duration<double>(1.0 / options.rate_hz));
        const auto start = std::chrono::steady_clock::now();

        // The prebuilt SDK constructor can block until it receives model
        // feedback. Observe it from another thread so the time limit and
        // Ctrl+C remain enforceable when the robot is unreachable.
        bool construction_finished = false;
        std::thread initializer_observer;
        const auto construction_deadline =
            start + std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::duration<double>(options.duration_seconds));

        if (options.duration_seconds > 0.0) {
            initializer_observer = std::thread([&]() {
                while (!construction_finished && !g_exit_now.load()) {
                    if (std::chrono::steady_clock::now() >= construction_deadline) {
                        std::cerr << "Timed out waiting for SDK model feedback; "
                                     "self-terminating the read-only process\n";
                        g_exit_now.store(true);
                        std::this_thread::sleep_for(std::chrono::milliseconds(200));
                        std::raise(SIGKILL);
                        return;
                    }
                    std::this_thread::sleep_for(std::chrono::milliseconds(50));
                }
            });
        }

        std::unique_ptr<zsibot::ZsibotExecutor> executor_storage;
        // ROLE_SDK without CMD_SDK_CONTROL_RIGHT remains read-only: SDK docs
        // state that SDK movement requires requesting control rights first.
        if (!g_exit_now.load()) {
            executor_storage = std::make_unique<zsibot::ZsibotExecutor>(
                zsibot::Role::ROLE_SDK,
                options.host,
                options.send_port,
                options.recv_port);
        }
        construction_finished = true;

        if (initializer_observer.joinable()) {
            initializer_observer.join();
        }

        if (g_exit_now.load()) {
            throw std::runtime_error("SDK initialization was interrupted or timed out");
        }

        zsibot::ZsibotExecutor& executor = *executor_storage;

        while (!g_exit_now.load()) {
            printState(executor);

            if (options.duration_seconds > 0.0) {
                const auto elapsed = std::chrono::steady_clock::now() - start;
                if (std::chrono::duration<double>(elapsed).count() >=
                    options.duration_seconds) {
                    break;
                }
            }

            std::this_thread::sleep_for(period);
        }
    } catch (const std::exception& error) {
        std::cerr << "Status monitor failed: " << error.what() << "\n";
        std::_Exit(1);
        return 1;
    }

    return 0;
}
