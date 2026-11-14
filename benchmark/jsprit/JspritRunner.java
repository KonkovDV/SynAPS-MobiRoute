// Runs jsprit on one VRPTW/CVRP instance for a wall-clock budget, one thread.
// Input (whitespace separated): n capacity fleet fixedCost seconds seed, then n
// rows "x y demand ready due service" (row 0 is the depot), then the n x n
// travel matrix (time = distance). Output: one "route i j k" line per vehicle,
// node indices as in the input, then "unassigned N" and "seconds S".
// The caller re-checks every route with its own verifier.

import com.graphhopper.jsprit.core.algorithm.VehicleRoutingAlgorithm;
import com.graphhopper.jsprit.core.algorithm.box.Jsprit;
import com.graphhopper.jsprit.core.algorithm.termination.TimeTermination;
import com.graphhopper.jsprit.core.problem.Location;
import com.graphhopper.jsprit.core.problem.VehicleRoutingProblem;
import com.graphhopper.jsprit.core.problem.job.Service;
import com.graphhopper.jsprit.core.problem.solution.VehicleRoutingProblemSolution;
import com.graphhopper.jsprit.core.problem.solution.route.VehicleRoute;
import com.graphhopper.jsprit.core.problem.solution.route.activity.TimeWindow;
import com.graphhopper.jsprit.core.problem.solution.route.activity.TourActivity;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleImpl;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleTypeImpl;
import com.graphhopper.jsprit.core.util.FastVehicleRoutingTransportCostsMatrix;
import com.graphhopper.jsprit.core.util.Solutions;
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.PrintWriter;
import java.util.Collection;
import java.util.Locale;
import java.util.Random;
import java.util.Scanner;

public final class JspritRunner {
    public static void main(String[] args) throws Exception {
        Scanner in = new Scanner(new BufferedReader(new FileReader(args[0])));
        in.useLocale(Locale.ROOT);
        int n = in.nextInt();
        int capacity = in.nextInt();
        int fleet = in.nextInt();
        double fixed = in.nextDouble();
        double seconds = in.nextDouble();
        long seed = in.nextLong();
        double[][] node = new double[n][6];
        for (int i = 0; i < n; i++) {
            for (int k = 0; k < 6; k++) {
                node[i][k] = in.nextDouble();
            }
        }
        FastVehicleRoutingTransportCostsMatrix.Builder matrix =
                FastVehicleRoutingTransportCostsMatrix.Builder.newInstance(n, false);
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double d = in.nextDouble();
                matrix.addTransportTimeAndDistance(i, j, d, d);
            }
        }
        VehicleTypeImpl type = VehicleTypeImpl.Builder.newInstance("type")
                .addCapacityDimension(0, capacity)
                .setFixedCost(fixed)
                .setCostPerDistance(1.0)
                .setCostPerTransportTime(0.0)
                .setCostPerWaitingTime(0.0)
                .build();
        VehicleRoutingProblem.Builder problem = VehicleRoutingProblem.Builder.newInstance();
        problem.setFleetSize(VehicleRoutingProblem.FleetSize.FINITE);
        Location depot = Location.Builder.newInstance().setIndex(0).setId("0").build();
        for (int v = 0; v < fleet; v++) {
            problem.addVehicle(VehicleImpl.Builder.newInstance("v" + v)
                    .setStartLocation(depot)
                    .setEndLocation(depot)
                    .setEarliestStart(node[0][3])
                    .setLatestArrival(node[0][4])
                    .setType(type)
                    .build());
        }
        for (int i = 1; i < n; i++) {
            Location at = Location.Builder.newInstance().setIndex(i).setId(Integer.toString(i)).build();
            problem.addJob(Service.Builder.newInstance(Integer.toString(i))
                    .addSizeDimension(0, (int) Math.round(node[i][2]))
                    .setLocation(at)
                    .setServiceTime(node[i][5])
                    .setTimeWindow(TimeWindow.newInstance(node[i][3], node[i][4]))
                    .build());
        }
        problem.setRoutingCost(matrix.build());
        VehicleRoutingProblem vrp = problem.build();
        VehicleRoutingAlgorithm algorithm = Jsprit.Builder.newInstance(vrp)
                .setProperty(Jsprit.Parameter.THREADS, "1")
                .setRandom(new Random(seed))
                .buildAlgorithm();
        algorithm.setMaxIterations(Integer.MAX_VALUE);
        // The clock starts when the algorithm announces its start: register it as
        // a listener too, or it measures from zero and stops at once.
        TimeTermination clock = new TimeTermination((long) (seconds * 1000.0));
        algorithm.addTerminationCriterion(clock);
        algorithm.addListener(clock);
        long started = System.nanoTime();
        Collection<VehicleRoutingProblemSolution> found = algorithm.searchSolutions();
        double elapsed = (System.nanoTime() - started) / 1e9;
        VehicleRoutingProblemSolution best = Solutions.bestOf(found);
        try (PrintWriter out = new PrintWriter(args[1], "UTF-8")) {
            for (VehicleRoute route : best.getRoutes()) {
                StringBuilder line = new StringBuilder("route");
                for (TourActivity activity : route.getActivities()) {
                    line.append(' ').append(activity.getLocation().getIndex());
                }
                out.println(line);
            }
            out.println("unassigned " + best.getUnassignedJobs().size());
            out.println("seconds " + elapsed);
        }
    }
}
