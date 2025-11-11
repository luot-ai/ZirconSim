#include "Statistic.h"
#include "utils.h"
#include <iostream>
#include <filesystem>

void Statistic::printPerformance() {
    std::cout << ANSI_FG_CYAN << "Total cycles: " << cycles << ", Total insts: " << insts << ", IPC: " << getIPC() << ANSI_NONE << std::endl;
}
void Statistic::printLastInstrucions(AXIMemory* mem){
    std::cout << ANSI_FG_CYAN << "Last 8 instructions:" << ANSI_NONE << std::endl;
    std::cout << ANSI_FG_MAGENTA;
    for(int i = 0; i < 8; i++){
        // 16进制输出，所有补全8位， 格式：xxxxxx: xxxxxxx
        std::cout << std::hex << std::setw(8) << std::setfill('0') << pcRingBuffer[(pcRingBufferIndex + i) % 8];
        std::cout << ": " << std::hex << std::setw(8) << std::setfill('0') << mem->debugRead(pcRingBuffer[(pcRingBufferIndex + i) % 8]) << std::dec << std::endl;
    }
    std::cout << ANSI_NONE;
}
void Statistic::printMarkdownReport(VCPU* cpu, std::string imgName, Simulator* sim){
    // 创建reports文件夹
    std::string reportsDir = "reports";
    if(!std::filesystem::exists(reportsDir)){
        std::filesystem::create_directory(reportsDir);
    }
    std::ofstream fout = std::ofstream("reports/report-" + imgName + ".md");

    fout << "## 程序基本情况" << std::endl;
    fout << "| 程序名 | 总周期数 | 总指令数 | IPC |" << std::endl;
    fout << "| --- | --- | --- | --- |" << std::endl;
    fout << "| " << imgName << " | " << cycles << " | " << insts << " | " << getIPC() << " |" << std::endl;

    fout << "### 指令统计" << std::endl;
    fout << "| 指令类型 | 总数 | 占比 |" << std::endl;
    fout << "| --- | --- | --- |" << std::endl;
    fout << "| ALU | " << sim->getInstStat().aluInsts << " | " << sim->getInstStat().aluInsts * 100.0 / insts << "% |" << std::endl;
    fout << "| Branch | " << sim->getInstStat().branchInsts << " | " << sim->getInstStat().branchInsts * 100.0 / insts << "% |" << std::endl;
    fout << "| Load | " << sim->getInstStat().loadInsts << " | " << sim->getInstStat().loadInsts * 100.0 / insts << "% |" << std::endl;
    fout << "| Store | " << sim->getInstStat().storeInsts << " | " << sim->getInstStat().storeInsts * 100.0 / insts << "% |" << std::endl;
    fout << "| Mul | " << sim->getInstStat().mulInsts << " | " << sim->getInstStat().mulInsts * 100.0 / insts << "% |" << std::endl;
    fout << "| Div | " << sim->getInstStat().divInsts << " | " << sim->getInstStat().divInsts * 100.0 / insts << "% |" << std::endl;

    uint32_t branchSuccess = cpu->io_dbg_cmt_bdb_branch - cpu->io_dbg_cmt_bdb_branchFail;
    double branchSuccessRate = cpu->io_dbg_cmt_bdb_branch != 0 ? branchSuccess * 100.0 / cpu->io_dbg_cmt_bdb_branch : 0.0;
    uint32_t callSuccess = cpu->io_dbg_cmt_bdb_call - cpu->io_dbg_cmt_bdb_callFail;
    double callSuccessRate = cpu->io_dbg_cmt_bdb_call != 0 ? callSuccess * 100.0 / cpu->io_dbg_cmt_bdb_call : 0.0;
    uint32_t retSuccess = cpu->io_dbg_cmt_bdb_ret - cpu->io_dbg_cmt_bdb_retFail;
    double retSuccessRate = cpu->io_dbg_cmt_bdb_ret != 0 ? retSuccess * 100.0 / cpu->io_dbg_cmt_bdb_ret : 0.0;

    fout << "## 分支预测" << std::endl;
    fout << "| 分支类型 | 总数 | 预测正确数 | 预测正确率 |" << std::endl;
    fout << "| --- | --- | --- | --- |" << std::endl;
    fout << "| Branch | " << cpu->io_dbg_cmt_bdb_branch << " | " << branchSuccess << " | " << branchSuccessRate << "% |" << std::endl;
    fout << "| Call | " << cpu->io_dbg_cmt_bdb_call << " | " << callSuccess << " | " << callSuccessRate << "% |" << std::endl;
    fout << "| Ret | " << cpu->io_dbg_cmt_bdb_ret << " | " << retSuccess << " | " << retSuccessRate << "% |" << std::endl;

    uint32_t iCacheVisit = cpu->io_dbg_fte_ic_visit;
    uint32_t iCacheHit = cpu->io_dbg_fte_ic_hit;
    double iCacheHitRate = iCacheVisit != 0 ? iCacheHit * 100.0 / iCacheVisit : 0.0;

    uint32_t dCacheRVisit = cpu->io_dbg_bke_lsPP_dc_0_visit;
    uint32_t dCacheRHit = cpu->io_dbg_bke_lsPP_dc_0_hit;
    double dCacheRHitRate = dCacheRVisit != 0 ? dCacheRHit * 100.0 / dCacheRVisit : 0.0;

    uint32_t dCacheWVisit = cpu->io_dbg_bke_lsPP_dc_1_visit;
    uint32_t dCacheWHit = cpu->io_dbg_bke_lsPP_dc_1_hit;
    double dCacheWHitRate = dCacheWVisit != 0 ? dCacheWHit * 100.0 / dCacheWVisit : 0.0;

    uint32_t l2ICacheVisit = cpu->io_dbg_l2_0_visit;
    uint32_t l2ICacheHit = cpu->io_dbg_l2_0_hit;
    double l2ICacheHitRate = l2ICacheVisit != 0 ? l2ICacheHit * 100.0 / l2ICacheVisit : 0.0;

    uint32_t l2DCacheVisit = cpu->io_dbg_l2_1_visit;
    uint32_t l2DCacheHit = cpu->io_dbg_l2_1_hit;
    double l2DCacheHitRate = l2DCacheVisit != 0 ? l2DCacheHit * 100.0 / l2DCacheVisit : 0.0;

    fout << "## 高速缓存" << std::endl;
    fout << "| 高速缓存通道 | 访问次数 | 命中数 | 命中率 |" << std::endl;
    fout << "| --- | --- | --- | --- |" << std::endl;
    fout << "| ICache Read | " << iCacheVisit << " | " << iCacheHit << " | " << iCacheHitRate << "% |" << std::endl;
    fout << "| DCache Read | " << dCacheRVisit << " | " << dCacheRHit << " | " << dCacheRHitRate << "% |" << std::endl;
    fout << "| DCache Write | " << dCacheWVisit << " | " << dCacheWHit << " | " << dCacheWHitRate << "% |" << std::endl;
    fout << "| L2Cache ICache | " << l2ICacheVisit << " | " << l2ICacheHit << " | " << l2ICacheHitRate << "% |" << std::endl;
    fout << "| L2Cache DCache | " << l2DCacheVisit << " | " << l2DCacheHit << " | " << l2DCacheHitRate << "% |" << std::endl;

    fout << "## 流水线停顿" << std::endl;
    fout << "### 前端" << std::endl;
    fout << "| 停顿原因 | 停顿周期数 | 停顿率 |" << std::endl;
    fout << "| --- | --- | --- |" << std::endl;
    fout << "| ICache缺失 | " << cpu->io_dbg_fte_ic_missCycle << " | " << cpu->io_dbg_fte_ic_missCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 发射队列满 | " << cpu->io_dbg_fte_fq_fullCycle << " | " << cpu->io_dbg_fte_fq_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 发射队列空 | " << cpu->io_dbg_fte_fq_emptyCycle << " | " << cpu->io_dbg_fte_fq_emptyCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 无空闲物理寄存器 | " << cpu->io_dbg_fte_rnm_fList_fListEmptyCycle << " | " << cpu->io_dbg_fte_rnm_fList_fListEmptyCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "### 调度" << std::endl;
    fout << "| 停顿原因 | 停顿周期数 | 停顿率 |" << std::endl;
    fout << "| --- | --- | --- |" << std::endl;
    fout << "| 重排序缓存满 | " << cpu->io_dbg_cmt_rob_fullCycle << " | " << cpu->io_dbg_cmt_rob_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 分支数据缓存满 | " << cpu->io_dbg_cmt_bdb_fullCycle << " | " << cpu->io_dbg_cmt_bdb_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "### 后端" << std::endl;
    fout << "| 停顿原因 | 停顿周期数 | 停顿率 |" << std::endl;
    fout << "| --- | --- | --- |" << std::endl;
    fout << "| 算数发射队列满 | " << cpu->io_dbg_bke_arIQ_fullCycle << " | " << cpu->io_dbg_bke_arIQ_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 乘除发射队列满 | " << cpu->io_dbg_bke_mdIQ_fullCycle << " | " << cpu->io_dbg_bke_mdIQ_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 访存发射队列满 | " << cpu->io_dbg_bke_lsIQ_fullCycle << " | " << cpu->io_dbg_bke_lsIQ_fullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 除法器运算 | " << cpu->io_dbg_bke_mdPP_srt2_busyCycle << " | " << cpu->io_dbg_bke_mdPP_srt2_busyCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| DCacahe缺失 | " << cpu->io_dbg_bke_lsPP_dc_0_missCycle << " | " << cpu->io_dbg_bke_lsPP_dc_0_missCycle * 100.0 / cycles  << "% |" << std::endl;
    fout << "| 写缓存满 | " << cpu->io_dbg_bke_lsPP_dc_0_sbFullCycle << " | " << cpu->io_dbg_bke_lsPP_dc_0_sbFullCycle * 100.0 / cycles  << "% |" << std::endl;
    fout.close();

}