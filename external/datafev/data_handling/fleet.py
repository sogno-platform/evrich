# The datafev framework

# Copyright (C) 2022,
# Institute for Automation of Complex Power Systems (ACS),
# E.ON Energy Research Center (E.ON ERC),
# RWTH Aachen University

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


from data_handling.vehicle import ElectricVehicle
import pandas as pd
from datetime import datetime
import mysql.connector


class EVFleet(object):
    """
    Class to define charging demand of an EV fleet.
    """

    def __init__(self, fleet_id, behavior, sim_horizon, service):
        """
        EVFleet objects are initialized by three data
        

        Parameters
        ----------
        fleet_id : str
            Identifier of the fleet.
        behavior : pd.DataFrame
            This is the input that determines the fleet behavior.
            It contains all necessary information defining the charging demand.
        sim_horizon : list or pd.date_range
            Iterable object that contains time steps in the simulation horizon.
        service: bool
            If true: Service to be used for the fleet.

        Returns
        -------
        None.

        """

        self.fleet_id = fleet_id
        self.objects = {}
        self.reserving_at = dict([(t, []) for t in sim_horizon])
        self.reserving_at[None] = []
        self.incoming_at = dict([(t, []) for t in sim_horizon])
        self.outgoing_at = dict([(t, []) for t in sim_horizon])
        self.outgoing_at[None] = []


        ##################################################################################################
        # Define behavior
        for _, i in behavior.iterrows():

            # Initialization of an EV object
            evID = i["vehicle_id"]
            evModel = i["vehicle_model"]
            bcap = i["battery_capacity_kWh"]
            p_max_ch = i["p_max_ch_kW"]
            p_max_ds = i["p_max_ds_kW"]
            ev = ElectricVehicle(evID, evModel, bcap, p_max_ch, p_max_ds)

            # Assigning the scenario parameters for requests
            ev.admitted = False
            ev.soc_tar_at_t_dep_est = i["demand_target_SoC"]
            ev.v2g_allow = i["v2g_allowance_kWh"] * 3600
            if service == True:
                ev.t_res = datetime.fromtimestamp(i["start_time"]) # Reservation time (=Start of drive after reservation)
                ev.t_res_unix = i["start_time"] # Reservation time (=Start of drive after reservation) in unix
                ev.soc_res = i["start_SoC"] # SoC at the reservation time
                ev.loc_res = i["start_location"] # Location of the EV at the reservation time
                ev.sj_loc_center = i["sojourn_location_center"]
                ev.sj_loc_radius = i["sojourn_location_radius"] # Desired sojourn location radius
                ev.sj_period = i["sojourn_period"] # Soujorn period of the EV at the Charging Station
            else:
                ev.t_arr_real = datetime.fromtimestamp(i["real_arrival_time"])
                ev.soc_arr_real = i["real_arrival_SoC"]
                ev.t_dep_real = datetime.fromtimestamp(i["real_departure_time"])
                ev.cluster_target = str(i["target_cluster"])
                ev.soc[ev.t_arr_real] = ev.soc_arr_real

            self.objects[evID] = ev

            if service == True:
                if pd.isna(ev.t_res):
                    self.reserving_at[None].append(ev)
                else:
                    self.reserving_at[ev.t_res].append(ev)
            
        ##################################################################################################

        ##################################################################################################
        # TODO: Calculate statistics: To be also done after the assignment of the aggregator
        #self.presence_distribution = {}
        #for t in sim_horizon:
        #    self.presence_distribution[t] = len(
        #        behavior[
        #            (behavior["Real Arrival Time"] <= t)
        #            & (behavior["Real Departure Time"] > t)
        #        ]
        #    )
        ##################################################################################################

    def enter_power_soc_table(self, table):
        """
        In practice, power that can be handled (withdrawn/injected) by EV 
        batteries change by SOC. This method is called to enter SOC dependency 
        data of the EVs in the scenario. SOC dependency is defined in a table.

        Parameters
        ----------
        table : pandas.DataFrame
            This table contains all EVs SOC dependency data. Each EV's data has the following parameters:
                - index --> Identifier of the SOC range,
                - SOC_LB --> Lower bound of a particular SOC range,
                - SOC_UB --> Upper bound of a particular SOC range,
                - P_LB --> Lower bound of power capability in a particular SOC range,
                - P_UB --> Upper bound of power capability in a particular SOC range.

        Returns
        -------
        None.

        """
        for ev_id, ev in self.objects.items():
            ev.pow_soc_table = table.loc[ev_id].copy()

    def reserving_vehicles_at(self, ts):
        """
        The method to query vehicles that place reservation request at a
        particular time step in simulatio.

        Parameters
        ----------
        ts : datetime
            The queried time step 

        Returns
        -------
        list
            The list of the objects that place reservation request at ts.

        """
        return self.reserving_at[ts]

    def incoming_vehicles_at(self, ts):
        """
        The method to query vehicles that arrive in charger clusters at a
        particular time step in simulation.

        Parameters
        ----------
        ts : datetime.datetime
            The queried time step. 

        Returns
        -------
        list
            The list of the objects that arrive in clusters at ts.

        """
        return self.incoming_at[ts]

    def outgoing_vehicles_at(self, ts):
        """
        The method to query vehicles that leave charger clusters at a
        particular time step in simulation.

        Parameters
        ----------
        ts : datetime
            The queried time step 

        Returns
        -------
        list
            The list of the objects that leave clusters at ts.

        """
        return self.outgoing_at[ts]

    def export_results_to_excel(self, start, end, step, xlfile):
        """
        This method is run after simulation to analyze the simulation results 
        related to the EV fleet. It exports simulation results to a xlsx file.

        Parameters
        ----------
        start : datetime.datetime
            Start of the period of investigation.
        end : datetime.datetime
            End of the period of investigation.
        step : datetime.timedelta
            Time resolution of the period of investigation.
        xlfile : str
            The name of the xlsx file to export results.

        Returns
        -------
        None.

        """

        sim_horizon = pd.date_range(start=start, end=end, freq=step)

        soc = pd.DataFrame(index=sim_horizon)
        g2v = pd.DataFrame(index=sim_horizon)
        v2g = pd.DataFrame(index=sim_horizon)
        status = pd.Series(dtype="float64")

        with pd.ExcelWriter(xlfile) as writer:

            for ev_id in sorted(self.objects.keys()):

                ev = self.objects[ev_id]

                soc.loc[:, ev_id] = pd.Series(ev.soc, dtype="float64")
                g2v.loc[:, ev_id] = pd.Series(ev.g2v, dtype="float64")
                v2g.loc[:, ev_id] = pd.Series(ev.v2g, dtype="float64")
                status[ev_id] = ev.admitted

            soc.to_excel(writer, sheet_name="SOC Trajectory")
            g2v.to_excel(writer, sheet_name="G2V Charge")
            v2g.to_excel(writer, sheet_name="V2G Discharge")
            status.to_excel(writer, sheet_name="Admitted")

