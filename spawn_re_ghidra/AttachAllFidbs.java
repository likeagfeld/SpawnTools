// Apply every Katana/Naomi/Kunoichi FIDB to the current program.
// Ghidra 12.0.4's FidFileManager API.
import ghidra.app.script.GhidraScript;
import ghidra.feature.fid.db.FidFileManager;
import ghidra.feature.fid.db.FidFile;
import java.io.File;

public class AttachAllFidbs extends GhidraScript {
    @Override
    public void run() throws Exception {
        File fidbDir = new File("D:/Ghidra Function IDs for Dreamcast Katana SDKs");
        if (!fidbDir.isDirectory()) {
            println("FIDB dir not found: " + fidbDir);
            return;
        }
        FidFileManager mgr = FidFileManager.getInstance();
        int attached = 0;
        for (File f : fidbDir.listFiles()) {
            if (!f.getName().toLowerCase().endsWith(".fidb")) continue;
            try {
                mgr.addUserFidFile(f);
                println("attached FIDB: " + f.getName());
                attached++;
            } catch (Exception e) {
                println("FAILED to attach " + f.getName() + ": " + e.getMessage());
            }
        }
        println("FIDBs attached: " + attached);
        analyzeAll(currentProgram);
        println("re-analysis complete");
    }
}
