import { Router } from 'express';
import { prisma } from '../db';

const router = Router();

router.get('/', async (req, res) => {
  try {
    const { days, startDate, endDate } = req.query;
    let dateFilter = {};
    
    if (startDate && endDate) {
      const start = new Date(startDate as string);
      start.setHours(0, 0, 0, 0);
      const end = new Date(endDate as string);
      end.setHours(23, 59, 59, 999);
      dateFilter = {
        createdAt: {
          gte: start,
          lte: end
        }
      };
    } else if (days && days !== 'all') {
      const daysInt = parseInt(days as string);
      if (!isNaN(daysInt)) {
        const targetDate = new Date();
        if (daysInt === 1) {
          targetDate.setHours(0, 0, 0, 0); // Start of today
        } else {
          targetDate.setDate(targetDate.getDate() - daysInt);
        }
        dateFilter = {
          createdAt: {
            gte: targetDate
          }
        };
      }
    }

    const totalTransactions = await prisma.transaction.count({
      where: dateFilter
    });
    
    const revenueAggregation = await prisma.transaction.aggregate({
      where: dateFilter,
      _sum: { totalAmount: true },
    });

    let expenseAggregation = { _sum: { amount: 0 } };
    try {
      expenseAggregation = await (prisma as any).expense.aggregate({
        where: dateFilter,
        _sum: { amount: true },
      });
    } catch (e) {
      // Ignored if expense table is not yet migrated/generated
    }
    
    const totalRevenue = revenueAggregation._sum.totalAmount || 0;
    const totalExpenses = expenseAggregation._sum?.amount || 0;
    
    const allTransactionsForHPP = await prisma.transaction.findMany({
      where: dateFilter,
      include: { items: true }
    });
    const totalHPP = allTransactionsForHPP.reduce((sum, tx) => sum + tx.items.reduce((itemSum, item) => itemSum + ((item.hpp || 0) * item.quantity), 0), 0);
    
    const netProfit = totalRevenue - totalHPP - totalExpenses;
    
    const totalCustomers = await prisma.customer.count();

    // Ambil top 5 pelanggan berdasarkan XP/Level
    const topCustomers = await prisma.customer.findMany({
      orderBy: { xp: 'desc' },
      take: 5,
    });

    const recentTransactions = await prisma.transaction.findMany({
      where: dateFilter,
      orderBy: { createdAt: 'desc' },
      take: 500, // Increased take to better represent 30 days if there are many transactions
      include: { items: { include: { menu: true } } }
    });

    const salesByDate: Record<string, number> = {};
    const menuPopularity: Record<string, {name: string, count: number}> = {};

    // Pre-populate dates for time series
    let numDays = 7;
    if (days === '1') numDays = 2; // Need at least 2 points for AreaChart
    else if (days && days !== 'all' && !isNaN(parseInt(days as string))) {
      numDays = parseInt(days as string);
      if (numDays < 2) numDays = 2;
    }

    if (days !== 'all') {
      for (let i = numDays - 1; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const dateStr = d.toLocaleDateString('id-ID', { month: 'short', day: 'numeric' });
        salesByDate[dateStr] = 0;
      }
    }

    recentTransactions.forEach(tx => {
      // Sales chart
      const dateStr = new Date(tx.createdAt).toLocaleDateString('id-ID', { month: 'short', day: 'numeric' });
      if (salesByDate[dateStr] === undefined) {
         salesByDate[dateStr] = 0;
      }
      salesByDate[dateStr] += tx.totalAmount;

      // Menu popularity
      tx.items.forEach(item => {
        const menuName = item.menu?.name || `Menu #${item.menuId}`;
        if (!menuPopularity[menuName]) {
          menuPopularity[menuName] = { name: menuName, count: 0 };
        }
        menuPopularity[menuName].count += item.quantity;
      });
    });

    // For 'all', ensure we have at least 2 points if there's only 1
    if (days === 'all' && Object.keys(salesByDate).length === 1) {
       const onlyDate = Object.keys(salesByDate)[0];
       salesByDate['Sebelumnya'] = 0;
    }

    // Format chart data
    let chartData = Object.keys(salesByDate).map(date => ({
      date,
      revenue: salesByDate[date],
    }));
    
    // Sort chronologically (assuming keys were inserted chronologically or we just rely on JS object insertion order which is preserved here)
    if (days === 'all' && chartData.length > 0 && chartData[chartData.length-1].date === 'Sebelumnya') {
       const last = chartData.pop();
       if (last) chartData.unshift(last); // move 'Sebelumnya' to the start
    }

    // Format top menus
    const popularMenus = Object.values(menuPopularity)
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);

    res.json({
      totalRevenue: totalRevenue,
      totalExpenses: totalExpenses,
      netProfit: netProfit,
      totalOrders: totalTransactions,
      totalCustomers: totalCustomers,
      topCustomers,
      chartData: chartData,
      popularMenus
    });
  } catch (error) {
    console.error('Error fetching analytics:', error);
    res.status(500).json({ error: 'Failed to fetch analytics', details: error instanceof Error ? error.message : String(error) });
  }
});

router.get('/reports', async (req, res) => {
  try {
    const { days, startDate, endDate } = req.query;
    let dateFilter = {};
    
    if (startDate && endDate) {
      const start = new Date(startDate as string);
      start.setHours(0, 0, 0, 0);
      const end = new Date(endDate as string);
      end.setHours(23, 59, 59, 999);
      dateFilter = {
        createdAt: {
          gte: start,
          lte: end
        }
      };
    } else if (days && days !== 'all') {
      const daysInt = parseInt(days as string);
      if (!isNaN(daysInt)) {
        const targetDate = new Date();
        if (daysInt === 1) {
          targetDate.setHours(0, 0, 0, 0); // Start of today
        } else {
          targetDate.setDate(targetDate.getDate() - daysInt);
        }
        dateFilter = {
          createdAt: {
            gte: targetDate
          }
        };
      }
    }

    const transactions = await prisma.transaction.findMany({
      where: dateFilter,
      orderBy: { createdAt: 'desc' },
      include: {
        customer: true,
        items: {
          include: {
            menu: true
          }
        }
      }
    });

    res.json(transactions);
  } catch (error) {
    console.error('Error fetching reports:', error);
    res.status(500).json({ error: 'Failed to fetch reports' });
  }
});

export default router;
