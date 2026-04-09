"""
Capture a set of DC voltage readings from a UNI-T UPO1054 oscilloscope in DVM mode over PyVISA,
then write timestamps and voltage values to CSV and print the average voltage.
"""

import pyvisa
import time
import csv

TUI_DOT_QUANTITY = 3
TUI_DOT_DELAY_S = 0.4

SCOPE_TIMEOUT_MS = 3000
SCOPE_SAMPLE_PERIOD_S = 0.2

SCPI_QUERY_DELAY_AFTER_WRITE_S = 0.1

DVM_ENABLE_ATTEMPT_LIMIT = 3
DVM_READING_QUANTITY = 50

def tui_delay():
    for _ in range(TUI_DOT_QUANTITY):
        print(".", end="", flush=True)
        time.sleep(TUI_DOT_DELAY_S)
    print("\n")

def scpi_write(instrument, cmd):
    try:
        instrument.write(cmd)
    except pyvisa.errors.VisaIOError as e:
        raise RuntimeError(f"SCPI write failed: {cmd}") from e

def scpi_query(instrument, cmd):
    try:
        return instrument.query(cmd).strip()
    except pyvisa.errors.VisaIOError as e:
        raise RuntimeError(f"SCPI query failed: {cmd}") from e

def main():

    scope = None

    try:
        print("~~~~ UPO1054 DVM: Average Voltage ~~~~")

        # Establish TCP/IP connection to UPO1054
        rm = pyvisa.ResourceManager()
        lan_node_ip = input(">> Please enter the IP address of the oscilloscope: ")
        try:
            scope = rm.open_resource("TCPIP0::" + lan_node_ip + "::inst0::INSTR")
        except pyvisa.errors.VisaIOError as e:
            raise RuntimeError(f"Failed to open oscilloscope at {lan_node_ip}: {e}") from e

        scope.timeout = SCOPE_TIMEOUT_MS

        print(f"\nConnection established to: {scope.query("*IDN?")}")

        tui_delay()

        # Configure DVM for DC voltage capture on channel 1
        print("~~ Configuring DVM settings ~~")

        scpi_write(scope, ":DVM:SOURC 1")
        dvm_source = scpi_query(scope, ":DVM:SOURC?") 
        if dvm_source[-1] != "1":
            raise RuntimeError("Failed to set DVM source to channel 1")
        print(f"DVM source set to: channel {dvm_source[-1]}")

        scpi_write(scope, ":DVM:MODE DC")
        dvm_mode = scpi_query(scope, ":DVM:MODE?")
        if dvm_mode != "DC":
            raise RuntimeError("Failed to set DVM mode to DC")
        print(f"DVM mode set to: {dvm_mode}")

        for _ in range(DVM_ENABLE_ATTEMPT_LIMIT):
            scpi_write(scope, ":DVM:ENAB 1")
            time.sleep(SCPI_QUERY_DELAY_AFTER_WRITE_S)
            if scpi_query(scope, ":DVM:ENAB?") == "1":
                break
        else:
            raise RuntimeError(f"Failed to enable DVM after {DVM_ENABLE_ATTEMPT_LIMIT} attempts")
        print("DVM enabled\n")

        tui_delay()

        # Read from DVM
        dvm_reading_count = DVM_READING_QUANTITY
        print("~~ Obtaining voltage measurement set from DVM ~~\n"
            + f"### Taking {dvm_reading_count} measurements, captured every ~200 ms ###\n")

        sample_period = SCOPE_SAMPLE_PERIOD_S
        v_dataset = []

        start_capture_time = time.monotonic()
        prev_sample_time = start_capture_time
        next_sample_time = start_capture_time + sample_period

        for _ in range(dvm_reading_count):
            now = time.monotonic()
            remaining_time = next_sample_time - now
            if remaining_time > 0:
                time.sleep(remaining_time)

            voltage_reading = float(scpi_query(scope, ":DVM:CURR?"))
            sample_timestamp = time.monotonic()

            elapsed = float(sample_timestamp - start_capture_time)
            delta = float(sample_timestamp - prev_sample_time)

            v_dataset.append((elapsed, delta, voltage_reading))

            prev_sample_time = sample_timestamp
            next_sample_time += sample_period

        print("~~ Writing data to CSV file ~~\n")

        tui_delay()
        
        file_saved = False
        csv_filename = "upo1054_voltage_readings.csv"

        try:
            with open(csv_filename, "x", newline="") as measurements:
                writer = csv.writer(measurements)
                writer.writerow(["elapsed_s", "delta_s", "voltage_v"])
                for elapsed, delta, voltage in v_dataset:
                    writer.writerow([f"{elapsed:.3f}", f"{delta:.3f}", f"{voltage:.4f}"])
            file_saved = True
        except FileExistsError:
            print(f"Warning: {csv_filename} already exists. Latest data was not saved.")

        print(f"\n~~ Calculating average voltage (n = {dvm_reading_count}) ~~")
        voltages = [row[2] for row in v_dataset]
        v_avg = sum(voltages) / len(voltages)
        print(f"{v_avg:.4g} V\n")

        print("~~ Status ~~")
        if file_saved:
            print(f"CSV saved to: ./{csv_filename}")
        else:
            print("CSV file was not saved. (see warnings)")

    except RuntimeError as e:
        print(f"Error: {e}")

    finally:
        if scope is not None:
            try:
                scope.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
