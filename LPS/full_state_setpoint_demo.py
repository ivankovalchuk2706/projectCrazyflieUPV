import time
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.position_hl_commander import PositionHlCommander
from cflib.crazyflie.log import LogConfig
from cflib.utils import uri_helper

# URI to the Crazyflie to connect to
URI = uri_helper.uri_from_env(default='radio://0/80/2M/E7E7E7E7E7')

def log_callback(timestamp, data, logconf):
    x = data['kalman.stateX']
    y = data['kalman.stateY']
    z = data['kalman.stateZ']
    
    # Variance (Error coefficients). The smaller the number, the better.
    # < 0.001 is perfect. > 0.01 is unstable.
    var_x = data['kalman.varPX']
    var_y = data['kalman.varPY']
    
    print(f"POS: X={x:.2f}, Y={y:.2f}, Z={z:.2f} | VAR (Error): X={var_x:.4f}, Y={var_y:.4f}")

def simple_hover():
    # Initialize the low-level drivers
    cflib.crtp.init_drivers()

    print(f"Connecting to {URI}...")
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        print("Connected.")

        # 1. Configure logging (10 times per second / 100ms)
        log_conf = LogConfig(name='HoverLog', period_in_ms=100)
        log_conf.add_variable('kalman.stateX', 'float')
        log_conf.add_variable('kalman.stateY', 'float')
        log_conf.add_variable('kalman.stateZ', 'float')
        # Add variance variables to monitor signal quality/confidence
        log_conf.add_variable('kalman.varPX', 'float')
        log_conf.add_variable('kalman.varPY', 'float')

        scf.cf.log.add_config(log_conf)
        log_conf.data_received_cb.add_callback(log_callback)
        log_conf.start()

        # 2. Reset Estimator (Mandatory for LPS!)
        print("Resetting Kalman Estimator...")
        scf.cf.param.set_value('kalman.resetEstimation', '1')
        time.sleep(0.1)
        scf.cf.param.set_value('kalman.resetEstimation', '0')
        
        print("Waiting 3 seconds for position lock...")
        time.sleep(3)

        # 3. FLIGHT SEQUENCE
        # x=0.0, y=0.0 - hold center. Height 0.5m.
        print("Taking off...")
        with PositionHlCommander(scf, x=0.0, y=0.0, z=0.0, default_height=0.5) as pc:
            
            print(">>> HOVERING (5 Seconds) <<<")
            # Just wait while the Commander holds the height/position
            time.sleep(5)
            
            print("Landing...")
            # Landing happens automatically when exiting the 'with' block

        # Stop logging
        log_conf.stop()

if __name__ == '__main__':
    simple_hover()
